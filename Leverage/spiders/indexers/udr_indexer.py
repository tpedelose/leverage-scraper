from __future__ import annotations

from Leverage.items import PropertyItem
from Leverage.spiders.indexers import IndexerSpider

from typing import TYPE_CHECKING, Generator

if TYPE_CHECKING:
    from scrapy import Item
    from scrapy.http import Response


class UDRPropertyIndexer(IndexerSpider):
    """
    Spider to index UDR properties from the UDR main properties page.
    """

    name: str = "udr_indexer"
    allowed_domains: list[str] = ["udr.com"]
    start_urls: list[str] = ["https://www.udr.com/search-apartments/"]
    company_name: str = "UDR"

    def parse(self, response: Response) -> Generator[Item]:
        # Save initial page for debugging
        self.save_page(response)

        # Follow links to location pages to get properties
        location_links = response.css(".location-list__item a")
        yield from response.follow_all(location_links, self.parse_location_page)  # type: ignore
        # TODO? Consider opening a ticket about the type: ignore here

    def parse_location_page(self, response: Response) -> Generator[PropertyItem]:
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
