from __future__ import annotations

import asyncio
import re
import scrapy
from datetime import datetime, timezone
from scrapy import Selector
from scrapy_playwright.page import PageMethod
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from urllib.parse import parse_qs, urlsplit
from Leverage.items import UnitItem, PromoItem
from Leverage.spiders.crawlers import ContentBlockerSpider

from typing import TYPE_CHECKING, AsyncGenerator

if TYPE_CHECKING:
    from scrapy.http import Response
    from playwright.async_api import Page
    from twisted.python.failure import Failure


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


class Repli360Spider(ContentBlockerSpider):
    """
    Spider to scrape apartment listings from websites using the Repli360 template engine.
    """

    custom_settings = {
        # TODO: Find way to speed this up. Seems to be some rate-limiting going on.
        "CONCURRENT_REQUESTS": 1,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
        # "PLAYWRIGHT_MAX_PAGES_PER_CONTEXT": 4,
    }

    name: str = "repli360"
    start_urls: list[str] = []

    blocked_resource_types = set(["font", "image", "media"])

    POPUP_CLOSE_BUTTON_SELECTOR = ".dmPopupClose"
    APT_DETAILS_TABLE_SELECTOR = "#fp_table1"
    APT_MODAL_SELECTOR = ".rrac_apartment_details"

    async def start(self):
        for url in self.start_urls:
            yield scrapy.Request(
                url=url,
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_methods": [
                        # Block unnecessary resources
                        PageMethod(
                            "route",
                            url="**/*",
                            handler=self.route_handler,
                        ),
                        # Ensure the main content is loaded
                        PageMethod("wait_for_load_state", "networkidle"),
                        # Wait a moment for the popup to appear
                        PageMethod(
                            "wait_for_selector",
                            self.POPUP_CLOSE_BUTTON_SELECTOR,
                        ),
                        # Close pop-up modal if it appears
                        PageMethod("click", self.POPUP_CLOSE_BUTTON_SELECTOR),
                        # Ensure the apartment listings tab is loaded
                        PageMethod("wait_for_selector", "#all_available_tab"),
                    ],
                },
                errback=self.handle_error,
            )

    async def parse(
        self, response: Response
    ) -> AsyncGenerator[UnitItem | PromoItem, None]:
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

    async def _click_and_wait(
        self,
        page: Page,
        click_selector: str,
        wait_selector: str,
        visible: bool = True,
        retries: int = 2,
        timeout: int = 30000,
    ) -> None:
        """Click a selector and wait for a DOM selector to become visible/hidden."""

        if await page.locator(click_selector).count() == 0:
            raise ValueError(f"Click selector '{click_selector}' not found on page.")

        try:
            await page.locator(click_selector).first.click()
        except PlaywrightTimeoutError as e:
            self.logger.debug(
                f"Initial click timeout for {click_selector} on page {page.url}: {e}"
            )

        total_tries = retries + 1  # initial try + retries
        state = "visible" if visible else "hidden"

        for attempt in range(1, total_tries + 1):
            exp_time = timeout * (2 ** (attempt - 1))  # exponential backoff

            try:
                # If a DOM selector is provided, wait for it
                await page.locator(wait_selector).first.wait_for(
                    state=state, timeout=exp_time
                )
                return
            except PlaywrightTimeoutError as e:
                self.logger.debug(
                    f"Playwright timeout during click (page {page.url}, attempt {attempt}): {e}"
                )
                if attempt >= retries:
                    self.logger.warning(
                        f"Final retry exhausted for _click_and_wait after timeout. Page: {page.url} (click: {click_selector} -> wait for: {wait_selector})"
                    )
                    raise e

            except Exception as e:
                self.logger.error(f"Error in _click_and_wait (attempt {attempt}): {e}")
                if attempt >= retries:
                    return

            # If we've reached here and there are remaining attempts, pause and retry.
            if attempt < retries:
                await page.wait_for_timeout(150)
                continue

    def parse_apartment_listing(self, selector: Selector) -> UnitItem:
        """
        Parse a single apartment listing row into a UnitItem.
        Kept synchronous so it can be reused outside async context (and easily unit-tested).
        """
        item = UnitItem()

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
            if not floorplan_id:
                self.logger.warning("Floorplan missing data-id attribute, skipping.")
                continue

            # Get from request directly to avoid timing issues with dynamic content
            anchor_selector = f'#all_available_tab .rracFloorplan[data-id="{floorplan_id}"] .right-cta a'
            async with page.expect_response("**/admin/getUnitListByFloor") as resp_info:
                await page.locator(anchor_selector).first.click()

            api_response = await resp_info.value
            data = await api_response.json()

            # Track scrape time after dynamic content has loaded
            scraped_dt = datetime.now(timezone.utc)
            today = scraped_dt.date()

            # Turn the returned HTML table into a Scrapy Selector for parsing
            html_response = data.get("str")
            table_sel = Selector(text=html_response)
            apartment_rows = table_sel.css(
                f"{self.APT_DETAILS_TABLE_SELECTOR} tr.unitlisting"
            )
            self.logger.info(f"Found {len(apartment_rows)} apartment listings.")

            # Get bath info from details, pattern usually "One Bedroom | 1 Bath |"
            floorplan_details = floorplan.css(".decp p::text").get()
            num_bathrooms = None
            if floorplan_details:
                bath_match = re.search(r"(\d+(\.\d+)?)\s*Bath", floorplan_details)
                if bath_match:
                    num_bathrooms = bath_match.group(1)
            for row in apartment_rows:
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
                listing["scraped_at"] = scraped_dt.isoformat()
                listing["floorplan_name"] = floorplan.attrib.get("data-fpname")
                listing["floorplan_id"] = floorplan.attrib.get("data-id")
                listing["num_bedrooms"] = floorplan.attrib.get("data-bed")
                listing["num_bathrooms"] = num_bathrooms
                listing["square_footage"] = floorplan.attrib.get("data-size")
                yield listing

            # close and restore state
            await self._click_and_wait(
                page,
                "#rrac_apartment_details .rrac_galleryClose",
                self.APT_MODAL_SELECTOR,
                visible=False,
            )

            # brief pause before next iteration to avoid rate limiting
            await asyncio.sleep(0.25)

        # Make sure to close the page to avoid hangs
        await page.close()

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

    async def handle_error(self, failure: Failure) -> None:
        try:
            page = failure.request.meta["playwright_page"]  # type: ignore[attr-defined]
            await page.close()
        except Exception as e:
            self.logger.error(f"Error closing Playwright page: {e}")
