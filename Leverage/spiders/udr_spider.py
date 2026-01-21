from __future__ import annotations

import scrapy
import json
from datetime import datetime, timezone
from scrapy_playwright.page import PageMethod
from Leverage.items import UnitItem, PromoItem
from Leverage.spiders.spider import ContentBlockerSpider, DatabaseSpider

from typing import TYPE_CHECKING, Generator

if TYPE_CHECKING:
    from scrapy.http import Response


class UDRSpider(DatabaseSpider, ContentBlockerSpider):
    """
    Spider to scrape apartment listings from UDR properties.
    """

    name: str = "udr"

    blocked_resource_types = set(["font", "image", "media"])
    blocked_domains = set(
        [
            "*://*.sierra.chat/*",
            "*://*.nestiolistings.com/*",
        ]
    )

    COMPANY_ID = 2  # Company ID in DB
    VIEWMODEL_VARIABLE_TEXT = "window.udr.jsonObjPropertyViewModel"

    async def start(self):
        for url in self.start_urls:
            yield scrapy.Request(
                url=url,
                meta={
                    "playwright": True,
                    "playwright_page_methods": [
                        # Block unnecessary resources
                        PageMethod(
                            "route",
                            url="**/*",
                            handler=self.route_handler,
                        ),
                        # Ensure the main content is loaded
                        PageMethod("wait_for_load_state", "networkidle"),
                    ],
                },
            )

    def parse(self, response: Response) -> Generator[UnitItem | PromoItem, None, None]:
        # Template has a view model embedded in a script tag in the head. We'll take that.
        script_content = response.xpath(
            f"//script[contains(., '{self.VIEWMODEL_VARIABLE_TEXT}')]/text()"
        ).get()
        if not script_content:
            self.logger.error("Script tag with target text not found.")
            return

        # Extract the target
        script_lines = script_content.strip().split("\n")
        view_model_line = next(
            (line for line in script_lines if self.VIEWMODEL_VARIABLE_TEXT in line),
            None,
        )
        if not view_model_line:
            self.logger.error("View model line not found in script content.")
            return

        # Load ViewModel from JSON
        view_model_json = (
            view_model_line.strip()
            .strip(";")
            .removeprefix(f"{self.VIEWMODEL_VARIABLE_TEXT} = ")
        )
        json_data = json.loads(view_model_json)
        scraped_at = datetime.now(timezone.utc).isoformat()

        # Parse data
        for promo in self.parse_specials(json_data):
            promo["scraped_at"] = scraped_at
            yield promo

        for unit in self.parse_floorplans(json_data):
            unit["scraped_at"] = scraped_at
            unit["property_url"] = response.url
            yield unit

    def parse_specials(self, json_data: dict) -> Generator[PromoItem, None, None]:
        """Parse specials from view model"""
        specials = json_data.get("allSpecials", [])
        for special in specials:
            yield PromoItem(
                # property_id=special.get("propertyId"),
                ext_floorplan_id=special.get("floorplanId"),
                ext_promo_id=special.get("id"),
                text=special.get("content"),
                has_available_units=special.get("hasAvailableUnits"),
            )

    def parse_floorplans(self, json_data: dict) -> Generator[UnitItem, None, None]:
        """Parse floor plans from view model"""
        floor_plans = json_data.get("floorPlans", [])
        for floor_plan in floor_plans:
            listings = floor_plan.get("units", [])
            for listing in listings:
                # TODO?: consider using ItemLoader
                item = UnitItem()

                # Price info
                item["rent_usd"] = listing.get("rent")
                item["deposit_usd"] = listing.get("deposit")
                item["admin_fee"] = floor_plan.get("id")
                item["application_fee"] = floor_plan.get("applicationFee")

                # Availability
                # TODO: Multiple "date available" items, not sure which is correct
                available_date = listing.get("earliestMoveInDate")
                if available_date:  # TODO? Try-except for parse errors?
                    available_date = (
                        self.parse_date_str(available_date).date().isoformat()
                    )
                item["available_date"] = available_date
                item["is_available"] = listing.get("isAvailable")
                item["min_lease_term_months"] = listing.get("leaseTerm")

                # Location
                building_name = listing.get("building")
                if building_name == "N/A":
                    building_name = None
                item["building_name"] = building_name
                item["floor_number"] = listing.get("floorNumber")
                item["top_floor"] = listing.get("IsOnTopFloor")

                # Floor Plan Metadata
                item["floorplan_name"] = listing.get("floorplanName")
                item["floorplan_id"] = listing.get("floorplanId")
                item["num_bedrooms"] = listing.get("bedrooms")
                item["num_bathrooms"] = listing.get("bathrooms")
                item["square_footage"] = listing.get("sqFt")

                # Identifiers
                item["unit_number"] = listing.get("marketingName")

                yield item

    def parse_date_str(self, date_str: str) -> datetime:
        # Expect strings like: "/Date(1773446400000+0000)/", "/Date(1773446400000)/",

        # Strip prefix/suffix
        date_str = date_str.removeprefix("/Date(").removesuffix(")/")

        # Split off timezone if present
        timestamp_str = date_str
        if "+" in date_str:
            timestamp_str, _ = date_str.split("+", 1)

        # TODO? Check if in milliseconds
        # Assume milliseconds for now
        ts_str = int(timestamp_str) / 1000
        dt = datetime.fromtimestamp(ts_str, tz=timezone.utc)
        return dt
