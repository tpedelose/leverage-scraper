from __future__ import annotations

import base64
import json
import scrapy
from scrapy import Selector, Spider
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit
from Leverage.items import UnitItem, PromoItem

from typing import TYPE_CHECKING, AsyncGenerator, Generator

if TYPE_CHECKING:
    from scrapy.http import Response


APT_DETAILS_LABEL_MAP = {
    # Price info
    "rent_usd": ["Starting At", "Total Monthly Leasing Price Starting At"],
    "deposit_usd": ["Deposit"],
    # Availability
    "available_date": ["Availability"],
    # Floor Plan Metadata
    "building_name": ["Building Number"],
    "unit_number": ["Unit Number"],
}


class Repli360Spider(Spider):
    """
    Spider to scrape apartment listings from websites using the Repli360 template engine.
    """

    name: str = "repli360"
    start_urls: list[str] = []

    blocked_resource_types = set(["font", "image", "media"])

    async def parse(self, response: Response):
        """
        Parse the main property page to find the rrac-website-script script tag.
        Use this to get the site_id needed to request property data.
        """

        # TODO: Add privacy policy scraping

        # Check for special promotions section
        yield self.parse_special(response)

        # Parse main content, starting with script
        if script_url := response.css(
            'script[src*="/rrac-website-script"]::attr(src)'
        ).get():
            yield scrapy.Request(
                url=script_url,
                callback=self.parse_script,
                cb_kwargs={"start_url": response.url},
            )

    def parse_special(self, response: Response) -> PromoItem | None:
        """
        Parse the special promotions section if available.
        """

        # Text is actually encoded as Base64 in a data attribute
        encoded_data = response.xpath(
            '//div[contains(@class, "headerWrapper")]//parent::*'
        ).attrib.get("data-widget-config")
        if not encoded_data:
            return

        try:
            decoded_bytes = base64.b64decode(encoded_data).decode("utf-8")
            json_data = json.loads(decoded_bytes)

            promo_texts = []
            for key in ("sliderTitle", "sliderDescription", "sliderDisclaimer"):
                if value := json_data.get(key):
                    if text := Selector(text=value).xpath("*//text()").get(""):
                        promo_texts.append(text.strip())

            return PromoItem(
                text="\n".join(promo_texts).strip(),
                scraped_at=datetime.now(timezone.utc).isoformat(),
                property_url=response.url,
            )

        except Exception as e:
            self.logger.error(f"Error decoding promotions data: {e}")

    async def parse_script(
        self, response: Response, **kwargs
    ) -> AsyncGenerator[scrapy.FormRequest]:
        """
        Parse the rrac-website-script to extract site_id and request property data.
        """

        arg_map = {
            "site_id": "site_id",
            "move_in_date": "desiredMoveinDate",
        }

        next_kwargs = {
            arg_name: response.css("::text").re_first(
                rf"var {var_name}\s*=\s*'([^']+)'"
            )
            or ""
            for arg_name, var_name in arg_map.items()
        }

        # Send post request to get property data
        yield scrapy.FormRequest(
            url="https://app.repli360.com/admin/template-render",
            method="POST",
            formdata={
                "site_id": next_kwargs["site_id"],
                "action": "",
                # "ready_script": "dom_load",
                "ready_script": "",
                "template_type": "",
                "source": "",
                "property_id": "",
            },
            callback=self.parse_property,
            cb_kwargs={**next_kwargs, "start_url": kwargs.get("start_url")},
        )

    async def parse_property(
        self, response: Response, site_id: str, move_in_date: str, **kwargs
    ) -> AsyncGenerator[scrapy.FormRequest]:
        """
        Parse the property data response to find available floorplans.
        """

        floorplans = response.css("#all_available_tab .rracFloorplan")
        self.logger.info(
            f"Found {len(floorplans)} available floorplans"
            + (f" on {kwargs.get('start_url')}." if "start_url" in kwargs else "")
        )

        for floorplan in floorplans:
            # Create a UnitItem for the floorplan that we can deepcopy later
            floorplan_item = UnitItem(
                property_url=kwargs.get("start_url"),
            )

            fp_info = self._parse_floorplan_card(floorplan)  # type: ignore
            if "units_available" in fp_info:
                del fp_info["units_available"]  # Not needed at floorplan level
            floorplan_item.update(fp_info)

            # Prefer explicit attributes if available
            floorplan_item.update(
                {
                    "floorplan_id": floorplan.attrib.get("data-id"),
                    "floorplan_name": floorplan.attrib.get("data-fpname"),
                    "num_bedrooms": floorplan.attrib.get("data-bed"),
                    "square_footage": floorplan.attrib.get("data-size"),
                }
            )

            # "getUnitListByFloor(this, 'B2A' , 2 , 2221,``);"
            # this, floorPlanID , template_type , site_id, _mode, _type='2d', _special='no'
            get_floor_func = floorplan.css(".right-sec a").attrib["onclick"]
            if not get_floor_func:
                self.logger.warning("No 'onclick' found for floorplan link, skipping.")
                continue

            get_floor_args = (
                get_floor_func.removeprefix("getUnitListByFloor(")
                .removesuffix(");")
                .split(",")
            )
            floorplan_id = get_floor_args[1].strip().strip("'")

            yield scrapy.FormRequest(
                url="https://app.repli360.com/admin/getUnitListByFloor",
                method="POST",
                formdata={
                    "floorPlanID": floorplan_id,
                    "moveinDate": move_in_date,
                    "site_id": site_id,
                    "template_type": "",
                    "mode": "apt",
                    "type": "2d",
                    "currentanuualterm": "",
                    "AcademicTerm": "",
                    "RentalLevel": "",
                    "special": "no",
                    "zpopUp": "",
                },
                callback=self.parse_unit_table,
                cb_kwargs={
                    "start_url": kwargs.get("start_url"),
                    "floorplan_item": floorplan_item,
                },
            )

    def parse_unit_table(self, response: Response, **kwargs) -> Generator[UnitItem]:
        # Get the units HTML
        response_json = json.loads(response.text)
        table_selector = Selector(
            text=response_json.get("str", "")
        )  # TODO? Turn into HTMLResponse

        floorplan_item: UnitItem | None = kwargs.get("floorplan_item")
        if not floorplan_item:
            self.logger.error("No floorplan_item passed to parse_unit_table.")
            return

        scraped_at = datetime.now(timezone.utc)
        today_date = scraped_at.date()

        units = table_selector.css("tr.unitlisting")
        self.logger.info(
            f"Found {len(units)} available units for floorplan {floorplan_item.get('floorplan_name')}"
            + (f" on {kwargs.get('start_url')}." if "start_url" in kwargs else "")
        )

        for unit in units:
            unit_item = floorplan_item.deepcopy()
            apt_info = self._parse_listing(unit)
            unit_item.update(apt_info)

            # Add floorplan-level metadata
            unit_item["scraped_at"] = scraped_at.isoformat()

            # Clean and process availability info
            available_date = unit_item.get("available_date")
            is_available = unit_item.get("is_available")
            if available_date:
                if available_date.lower() == "available now":
                    available_date = today_date
                else:
                    available_date = datetime.strptime(
                        available_date, "%m-%d-%Y"
                    ).date()
                if is_available is None:
                    is_available = available_date <= today_date
                available_date = available_date.isoformat()
            unit_item["available_date"] = available_date
            unit_item["is_available"] = is_available

            yield unit_item

    def _parse_floorplan_card(self, selector: Selector) -> dict[str, str]:
        """
        Get floorplan info from text, e.g., "2 Bed | 2 Bath | 1,200 Sq Ft | 5 Units Available"
        """

        # TODO: Make this more robust to potential HTML changes
        fp_desc = selector.css(".decp p::text").get()

        fp_info = {}
        if fp_desc:
            parts = [part.strip() for part in fp_desc.split("|")]

            for part in parts:
                if "Bed" in part:
                    fp_info["num_bedrooms"] = part.split(" ")[0].strip()
                elif "Bath" in part:
                    fp_info["num_bathrooms"] = part.split(" ")[0].strip()
                elif "Sq. Ft." in part:
                    fp_info["square_footage"] = part.split(" ")[0].strip()
                elif "Units Available" in part:
                    fp_info["units_available"] = part.split(" ")[0].strip()

        return fp_info

    def _parse_listing(self, selector: Selector) -> dict[str, str]:
        item = {}
        for field_key, label_texts in APT_DETAILS_LABEL_MAP.items():
            for label_text in label_texts:
                value = self._get_apt_data_by_label(selector, label_text)
                if value is not None:
                    item[field_key] = value
                    break  # Stop after finding the first matching label

        lease_link = selector.css('a[id^="goto_lease_"]::attr(href)').get()
        if lease_link and "?" in lease_link:
            qs = parse_qs(urlsplit(lease_link).query)
            if "BuildingID" in qs:
                item["building_name"] = qs["BuildingID"][0]
            if "Term" in qs:
                item["min_lease_term_months"] = qs["Term"][0]

        return item

    def _get_apt_data_by_label(
        self, row_selector: Selector, label_text: str
    ) -> str | None:
        """
        Finds data in a <td> by looking for a child <span> with matching text.

        Args:
            row_selector: The Scrapy Selector for the <tr>.
            label_text: The text of the <span> label to search for (e.g., "Unit Number").
        """

        # Find the <td> that contains the label <span>
        cell = row_selector.xpath(f".//td[span[contains(text(), '{label_text}')]]")
        if not cell:
            self.logger.debug(f"Label '{label_text}' not found in row.")
            return

        # Find direct text nodes of the <td>, ingoring child elements
        value_nodes = cell.xpath("./text()[normalize-space()]").getall()

        # If there's a rent matrix link, prefer direct text of <span> with class
        # TODO: (later) Scrape the full rent matrix
        if not value_nodes:
            value_nodes = cell.xpath(
                ".//span[contains(@class, 'term_plan_matrix_wrapper')]/text()"
            ).getall()

        # Join all direct text nodes and clean them up
        if value_nodes:
            return " ".join(value_nodes).strip().strip("$").replace(",", "")

        # If no direct text or matrix span was found, find text inside a child element
        # that is NOT the <span> label.
        value = cell.xpath("./*[not(self::span)]//text()").get()
        if value:
            return value.strip()

        return None
