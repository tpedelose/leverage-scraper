from datetime import datetime, timezone
from pathlib import Path
from scrapy_playwright.page import PageMethod
from Leverage.items import UnitItem, PromoItem
from Leverage.spiders.spider import ConfigurableSpider
from typing import Generator, List

import scrapy
import json


class UDRSpider(ConfigurableSpider):
    """
    Spider to scrape apartment listings from UDR properties.
    """

    name: str = "udr"
    start_urls: List[str] = []

    VIEWMODEL_VARIABLE_TEXT = "window.udr.jsonObjPropertyViewModel"

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

    def parse(self, response):
        self.logger.info("Saving initial page content.")
        filename = f"output/{self.name}_page_loaded.html"
        Path(filename).write_bytes(response.body)

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
        # json.dump(json_data, open(f"output/{self.name}_viewmodel.json", "w"), indent=2)

        scraped_time = datetime.now(timezone.utc).isoformat()

        # Parse data
        yield from self.parse_specials(json_data)
        yield from self.parse_floorplans(json_data)

    def parse_specials(
        self, json_data: dict, scraped_time=datetime
    ) -> Generator[PromoItem, None, None]:
        """Parse specials from view model"""
        specials = json_data.get("allSpecials", [])
        for special in specials:
            yield PromoItem(
                scraped_at=scraped_time,
                property_id=special.get("propertyId"),
                ext_floorplan_id=special.get("floorplanId"),
                ext_promo_id=special.get("id"),
                specials_text=special.get("content"),
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

                # TODO: come back to this and fill out more fields
                # Price info
                item["rent_usd"] = listing.get("rent")
                item["deposit_usd"] = listing.get("deposit")
                item["admin_fee"] = floor_plan.get("id")
                item["application_fee"] = floor_plan.get("applicationFee")

                # Availability
                # TODO: Multiple "date available" items, not sure which is correct
                item["available_date"] = listing.get("earliestMoveInDate")
                item["is_available"] = listing.get("isAvailable")
                item["min_lease_term_months"] = listing.get("leaseTerm")

                # Location
                item["building_name"] = listing.get("building")
                item["floor_number"] = listing.get("floorNumber")
                item["top_floor"] = listing.get("IsOnTopFloor")

                # Floor Plan Metadata
                item["floorplan_name"] = listing.get("floorplanName")
                item["floorplan_id"] = listing.get("floorplanId")
                item["num_bedrooms"] = listing.get("bedrooms")
                item["num_bathrooms"] = listing.get("bathrooms")
                item["square_footage"] = listing.get("sqFt")
                item["unit_number"] = listing.get("marketingName")

                yield item

    async def handle_error(self, failure):
        try:
            page = failure.request.meta["playwright_page"]
            await page.close()
        except Exception as e:
            self.logger.error(f"Error closing Playwright page: {e}")
