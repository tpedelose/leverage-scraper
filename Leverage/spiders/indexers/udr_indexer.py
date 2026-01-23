from __future__ import annotations

import scrapy
from pathlib import Path
from Leverage.items import PropertyItem

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scrapy.http import Response


class UDRPropertyIndexer(scrapy.Spider):
    """
    Spider to index UDR properties from the UDR main properties page.
    """

    name: str = "udr_indexer"
    allowed_domains: list[str] = ["udr.com"]
    start_urls: list[str] = ["https://www.udr.com/search-apartments/"]
    company_name: str = "UDR"

    async def start(self):
        for url in self.start_urls:
            yield scrapy.Request(url=url)

    def parse(self, response: Response):
        self.logger.info("Saving initial page content.")
        filename = f"output/{self.name}_page_loaded.html"
        Path(filename).write_bytes(response.body)

        # Extract property links from the main properties page
        location_links = response.css(
            ".location-list__item a.location-list__item-link::attr(href)"
        ).getall()
        for link in location_links:
            yield scrapy.Request(
                url=response.urljoin(link),
                callback=self.parse_location_page,
            )

    def parse_location_page(self, response: Response):
        self.logger.info(f"Parsing location page: {response.url}")

        cards = response.css(".community-card")
        for card in cards:
            property_link = card.css("a.community-card__title::attr(href)").get()
            if not property_link:
                self.logger.warning("No property link found for community card.")
                continue

            city_state_zip = card.css(".community-card__city-state::text").get()
            if not city_state_zip:
                self.logger.warning("No city/state/zip found for community card.")
                continue

            # TODO: consider switch to `usaddress` parsing
            city, state_zip = city_state_zip.split(", ")
            state, zip_code = state_zip.split(" ")

            apt_list_url = response.urljoin(
                "/".join([property_link, "apartments-pricing"]).replace("//", "/")
            )

            yield PropertyItem(
                company_name=self.company_name,
                property_name=card.css(".community-card__title-link::text").get(),
                address=card.css(".community-card__number-street::text").get(),
                city=city,
                state=state,
                postal_code=zip_code,
                template_engine="udr",
                url=apt_list_url,
            )
