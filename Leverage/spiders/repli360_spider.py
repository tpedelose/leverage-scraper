from __future__ import annotations

import re
import scrapy
from datetime import datetime, timezone
from pathlib import Path
from scrapy_playwright.page import PageMethod
from urllib.parse import parse_qs, urlsplit
from Leverage.items import UnitItem, PromoItem
from Leverage.spiders.spider import ConfigurableSpider

from typing import TYPE_CHECKING, AsyncGenerator

if TYPE_CHECKING:
    from scrapy.http import Response
    from playwright.async_api import Page
    from scrapy import Selector
    from twisted.python.failure import Failure


APT_DETAILS_LABEL_MAP = {
    # Price info
    "rent_usd": "Starting At",
    "deposit_usd": "Deposit",
    # Availability
    "available_date": "Availability",
    # Floor Plan Metadata
    "building_id": "Building Number",
    "unit_number": "Unit Number",
}


class Repli360Spider(ConfigurableSpider):
    """
    Spider to scrape apartment listings from websites using the Repli360 template engine.
    """

    name: str = "repli360"
    start_urls: list[str] = []

    POPUP_CLOSE_BUTTON_SELECTOR = ".dmPopupClose"
    APT_DETAILS_TABLE_SELECTOR = "#fp_table1"

    async def start(self):
        for url in self.start_urls:
            yield scrapy.Request(
                url=url,
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_methods": [
                        # Ensure the main content is loaded
                        PageMethod("wait_for_load_state", "networkidle"),
                        # Close pop-up modal if it appears
                        PageMethod("wait_for_timeout", 1000),
                        # Wait a moment for the popup to appear
                        PageMethod(
                            "wait_for_selector", self.POPUP_CLOSE_BUTTON_SELECTOR
                        ),
                        PageMethod("click", self.POPUP_CLOSE_BUTTON_SELECTOR),
                        # Wait for the dynamic content to load
                        PageMethod("wait_for_selector", "#all_available_tab"),
                        # Take a screenshot after page load (for debugging purposes)
                        PageMethod(
                            "screenshot",
                            path=Path(f"output/{self.name}_page_loaded.png"),
                            full_page=True,
                        ),
                    ],
                },
                errback=self.handle_error,
            )

    async def parse(
        self, response: Response
    ) -> AsyncGenerator[UnitItem | PromoItem, None]:
        self.logger.info("Saving initial page content.")
        filename = f"output/{self.name}_page_loaded.html"
        Path(filename).write_bytes(response.body)

        yield self.parse_specials(response)
        async for apt in self.parse_floorplans(response):
            apt["property_url"] = response.url
            yield apt

    def parse_specials(self, response: Response) -> PromoItem:
        # NOTE: Assumes only one specials header block
        header_info = response.css(".headerWrapper")
        deals_text = header_info.css("::text").getall()
        deals_text = [info.strip() for info in deals_text if info.strip()]
        self.logger.info(f"Extracted deals info: {deals_text}")
        return PromoItem(
            text=" ".join(deals_text),
            scraped_at=datetime.now(timezone.utc).isoformat(),
            property_url=response.url,
        )

    # small helper to avoid repeating click+wait logic
    async def _click_and_wait(
        self, page: Page, click_selector: str, wait_selector: str, visible: bool = True
    ):
        await page.click(click_selector)
        await page.wait_for_timeout(500)  # 500 ms delay to allow for animations
        state = "visible" if visible else "hidden"
        await page.wait_for_selector(wait_selector, state=state)

    def parse_apartment_listing(self, selector: Selector) -> UnitItem:
        """
        Parse a single apartment listing row into a UnitItem.
        Kept synchronous so it can be reused outside async context (and easily unit-tested).
        """
        item = UnitItem()

        for field_key, label_text in APT_DETAILS_LABEL_MAP.items():
            value = self._get_apt_data_by_label(selector, label_text)
            if value is not None:
                item[field_key] = value

        lease_link = selector.css('a[id^="goto_lease_"]::attr(href)').get()
        if lease_link and "?" in lease_link:
            qs = parse_qs(urlsplit(lease_link).query)
            if "BuildingID" in qs:
                item["building_name"] = qs["BuildingID"][0]
            if "Term" in qs:
                item["min_lease_term_months"] = qs["Term"][0]

        return item

    async def parse_floorplans(
        self, response: Response
    ) -> AsyncGenerator[UnitItem, None]:
        page = response.meta["playwright_page"]

        # Get the list of floor plans
        floorplans = response.css("#all_available_tab .rracFloorplan")
        self.logger.info(f"Found {len(floorplans)} available floorplans.")

        for floorplan in floorplans:
            # Click the anchor to load the floor plan details
            floorplan_id = floorplan.attrib.get("data-id")
            anchor_selector = f'.rracFloorplan[data-id="{floorplan_id}"] .right-cta a'
            await self._click_and_wait(
                page, anchor_selector, self.APT_DETAILS_TABLE_SELECTOR, visible=True
            )

            # Get the updated HTML content after dynamic loading
            new_response = response.replace(
                body=await page.content(), url=page.url, encoding="utf-8"
            )
            # Track scrape time after dynamic content has loaded
            scraped_at_utc = datetime.now(timezone.utc).isoformat()

            apartment_rows = new_response.css(
                f"{self.APT_DETAILS_TABLE_SELECTOR} tr.unitlisting"
            )
            self.logger.info(f"Found {len(apartment_rows)} apartment listings.")

            # Get bathroom info from floorplan details if available
            # Pattern of text is usually "One Bedroom | 1 Bath |"
            floorplan_details = floorplan.css(".decp p::text").get()
            num_bathrooms = None
            if floorplan_details:
                bath_match = re.search(r"(\d+(\.\d+)?)\s*Bath", floorplan_details)
                if bath_match:
                    num_bathrooms = bath_match.group(1)

            today = datetime.now(timezone.utc).date()
            for row in apartment_rows:
                # TODO: Switch to updating items with
                listing = self.parse_apartment_listing(row)

                # Clean and process availability info
                available_date = listing.get("available_date")
                is_available = listing.get("is_available")
                if available_date:
                    if available_date.lower() == "available now":
                        available_date = today
                    else:
                        available_date = datetime.strptime(
                            available_date, "%m-%d-%Y"
                        ).date()
                    if is_available is None:
                        is_available = available_date <= today
                    available_date = available_date.isoformat()
                listing["available_date"] = available_date
                listing["is_available"] = is_available

                # Add floorplan-level metadata
                listing["scraped_at"] = scraped_at_utc
                listing["floorplan_name"] = floorplan.attrib.get("data-fpname")
                listing["floorplan_id"] = floorplan.attrib.get("data-id")
                listing["num_bedrooms"] = floorplan.attrib.get("data-bed")
                listing["num_bathrooms"] = num_bathrooms
                listing["square_footage"] = floorplan.attrib.get("data-size")
                yield listing

            # close and restore state
            apt_details_close_selector = ".rrac_galleryClose"

            await self._click_and_wait(
                page,
                apt_details_close_selector,
                self.APT_DETAILS_TABLE_SELECTOR,
                visible=False,
            )

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

        # Try to find direct text nodes of the <td>, ingoring child elements
        value_nodes = cell.xpath("./text()[normalize-space()]").getall()
        if value_nodes:
            # Join all direct text nodes and clean them up
            return " ".join(value_nodes).strip().strip("$").replace(",", "")

        # If no direct text was found, find text inside a child element
        # that is NOT the <span> label.
        value = cell.xpath("./*[not(self::span)]//text()").get()
        if value:
            return value.strip()

    async def handle_error(self, failure: Failure) -> None:
        try:
            page = failure.request.meta["playwright_page"]  # type: ignore[attr-defined]
            await page.close()
        except Exception as e:
            self.logger.error(f"Error closing Playwright page: {e}")
