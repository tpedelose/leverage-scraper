from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from scrapy_playwright.page import PageMethod
from scrapy.loader import ItemLoader
from Leverage.items import ApartmentListingItem
from typing import AsyncGenerator, Dict, Any, Generator

import scrapy


FLOORPLAN_ITEM_MAP = {
    'data-fpname': 'floorplan_name',
    'data-id': 'floorplan_id',
    'data-bed': 'num_bedrooms',
    'data-size': 'floor_area',
    'data-min-price': 'price_min',
    'data-max-price': 'price_max',
}

APT_DETAILS_LABEL_MAP = {
    'building_id': 'Building Number',
    'unit_number': 'Unit Number',
    'deposit': 'Deposit',
    'rent': 'Starting At',
    'date_available': 'Availability',
}


class Repli360Spider(scrapy.Spider):
    """
    Spider to scrape apartment listings from websites using the Repli360 template engine.
    """

    name = "repli360"
    start_urls=[
        # Put desired URLs here
    ]

    # centralized constants
    POPUP_CLOSE_BUTTON_SELECTOR = '.dmPopupClose'
    DYNAMIC_CONTENT_SELECTOR = '#all_available_tab'
    FLOORPLAN_SELECTOR = '#all_available_tab .rracFloorplan'
    APT_DETAILS_TABLE_SELECTOR = '#fp_table1'
    APT_DETAILS_CLOSE_SELECTOR = '.rrac_galleryClose'
    CLICK_DELAY_MS = 500

    async def start(self):
        """
        Generates the initial request to load the dynamic page using Playwright.
        """
        for url in self.start_urls:
            yield scrapy.Request(
                url=url, # TODO: iterate over all start_urls
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_methods": [
                        # Ensure the main content is loaded
                        PageMethod("wait_for_load_state", "networkidle"),

                        # Close pop-up modal if it appears
                        PageMethod("wait_for_timeout", 1000),  # Wait a moment for the popup to appear
                        PageMethod("wait_for_selector", self.POPUP_CLOSE_BUTTON_SELECTOR), 
                        PageMethod("click", self.POPUP_CLOSE_BUTTON_SELECTOR),

                        # Wait for the dynamic content to load
                        PageMethod("wait_for_selector", self.DYNAMIC_CONTENT_SELECTOR),

                        # Take a screenshot after page load (for debugging purposes)
                        PageMethod("screenshot", path=Path(f"output/{self.name}_page_loaded.png"), full_page=True),
                    ],
                },
                errback=self.handle_error
            )

    async def parse(self, response) -> AsyncGenerator[ApartmentListingItem, None]:
        self.logger.info("Saving initial page content.")
        filename = f"output/{self.name}_page_loaded.html"
        Path(filename).write_bytes(response.body)
        
        # TODO: Parse header for deals info
        # self.parse_deals_info(response)
        async for apt in self.parse_floorplans(response):
            yield apt
    
    def parse_deals_info(self, response):
        header_info = response.css('.headerWrapper')
        deals_text = header_info.css('::text').getall()
        deals_text = [info.strip() for info in deals_text if info.strip()]
        self.logger.info(f"Extracted deals info: {deals_text}")
        return deals_text

    # small helper to avoid repeating click+wait logic
    async def _click_and_wait(self, page, click_selector, wait_selector, visible=True):
        await page.click(click_selector)
        await page.wait_for_timeout(self.CLICK_DELAY_MS)
        state = 'visible' if visible else 'hidden'
        await page.wait_for_selector(wait_selector, state=state)

    async def parse_floorplans(self, response) -> AsyncGenerator[ApartmentListingItem, None]:
        # Get the Playwright Page object from the response meta (Crucial!)
        page = response.meta["playwright_page"]
        
        # Get the list of floor plans
        floorplans = list(response.css(self.FLOORPLAN_SELECTOR))
        self.logger.info(f"Found {len(floorplans)} available floorplans.")

        for idx, fp in enumerate(floorplans):

            # Get the floor plan metadata
            print(fp.attrib)
            fp_meta: Dict[str, Any] = {map_key: fp.attrib.get(key, None) for key, map_key in FLOORPLAN_ITEM_MAP.items()}

            # Click the anchor to load the floor plan details
            self.logger.debug(f"Clicking anchor {idx + 1} of {len(floorplans)}")
            anchor_selector = f'.rracFloorplan[data-id="{fp_meta["floorplan_id"]}"] .right-cta a'
            await self._click_and_wait(page, anchor_selector, self.APT_DETAILS_TABLE_SELECTOR, visible=True)

            # Get the updated HTML content
            new_html = await page.content()
            new_response = response.replace(body=new_html, url=page.url, encoding='utf-8')

            # Convert parsed listing dicts into ApartmentListingItem via ItemLoader
            for listing in self.parse_apartment_listings(new_response):
                
                loader = ItemLoader(item=ApartmentListingItem())
                
                # Only load keys that are declared on the ApartmentListingItem.
                allowed_fields = set(ApartmentListingItem.fields.keys())
                
                # merge fp_meta and listing so we dedupe/override predictably (listing wins)
                merged = {**fp_meta, **listing}
                for k, v in merged.items():
                    if k in allowed_fields:
                        loader.add_value(k, v)
                    else:
                        # Debug log any keys that aren't part of the item schema
                        self.logger.debug(f"Skipping unknown field: {k} -> {v}")
                
                item = loader.load_item()
                self.logger.debug(f"Yielding ApartmentListingItem: {item}")
                yield item

            # close and restore state
            await self._click_and_wait(page, self.APT_DETAILS_CLOSE_SELECTOR, self.APT_DETAILS_TABLE_SELECTOR, visible=False)

            # TODO: Turn this into something that happens conditionally based on a debug flag or error handling
            # Take a screenshot after clicking (for debugging purposes)
            # await page.screenshot(path=Path(f"{self.name}_after_click_{idx + 1}.png"), full_page=True)

            # Save the updated content to a file
            # Path(f"{self.name}_floorplan_{idx + 1}.html").write_text(new_html, encoding="utf-8")

    def parse_apartment_listings(self, response) -> Generator[Dict[str, str], None, None]:
        """
        Parse apartment rows from the floorplan table and yield plain dicts.
        Kept synchronous so it can be reused outside async context (and easily unit-tested).
        """

        apartment_rows = list(response.css(f'{self.APT_DETAILS_TABLE_SELECTOR} tr.unitlisting'))
        self.logger.info(f"Found {len(apartment_rows)} apartment listings.")

        for row in apartment_rows:
            item = {}

            for field_key, label_text in APT_DETAILS_LABEL_MAP.items():
                value = self._get_apt_data_by_label(row, label_text)
                if value is not None:
                    item[field_key] = value

            lease_link = row.css('a[id^="goto_lease_"]::attr(href)').get()
            if lease_link and '?' in lease_link:
                qs = parse_qs(urlsplit(lease_link).query)
                if 'BuildingID' in qs:
                    item['building_id'] = qs['BuildingID'][0]
                if 'Term' in qs:
                    item['lease_term'] = qs['Term'][0]

            yield item

    def _get_apt_data_by_label(self, row_selector, label_text: str) -> str | None:
        """
        Finds data in a <td> by looking for a child <span> with matching text.
        
        Args:
            row_selector: The Scrapy Selector for the <tr>.
            label_text: The text of the <span> label to search for (e.g., "Unit Number").
        """

        # Find the <td> that contains the label <span>
        cell = row_selector.xpath(f".//td[span[contains(text(), '{label_text}')]]")
        if not cell:
            return None # The label wasn't found in this row

        # --- Strategy 1: Find direct text nodes (e.g., "$2,770") ---
        # This selects text nodes that are direct children of the <td>
        # and are not just whitespace. This ignores text inside <a>, <svg>, etc.
        value_nodes = cell.xpath('./text()[normalize-space()]').getall()
        if value_nodes:
            # Join all direct text nodes and clean them up
            value = " ".join(value_nodes).strip().strip('$').replace(',', '')
            return value

        # --- Strategy 2: Find text in a child tag (e.g., "<b>219</b>") ---
        # If no direct text was found, find text inside a child element
        # that is NOT the <span> label itself.
        value = cell.xpath("./*[not(self::span)]//text()").get()
        if value:
            return value.strip()
            
        return None # No value found

    async def handle_error(self, failure):
        page = failure.request.meta["playwright_page"]
        await page.close()
