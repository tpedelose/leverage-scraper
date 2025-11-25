import scrapy
from pathlib import Path
from urllib.parse import urljoin
from Leverage.items import PropertyItem


class UDRPropertyIndexer(scrapy.Spider):
    """
    Spider to index UDR properties from the UDR main properties page.
    """

    name: str = "udr_index"
    allowed_domains: list[str] = ["udr.com"]
    start_urls: list[str] = ["https://www.udr.com/search-apartments/"]

    LOCATION_LINK_SELECTOR = (
        ".location-list__item a.location-list__item-link::attr(href)"
    )

    async def start(self):
        for url in self.start_urls:
            yield scrapy.Request(url=url)

    def parse(self, response):
        self.logger.info("Saving initial page content.")
        filename = f"output/{self.name}_page_loaded.html"
        Path(filename).write_bytes(response.body)

        # Extract property links from the main properties page
        location_links = response.css(self.LOCATION_LINK_SELECTOR).getall()
        for link in location_links:
            yield scrapy.Request(
                url=response.urljoin(link),
                callback=self.parse_location_page,
            )

    def parse_location_page(self, response):
        self.logger.info(f"Parsing location page: {response.url}")
        filename = f"output/{self.name}_location_page.html"
        Path(filename).write_bytes(response.body)

        cards = response.css(".community-card")
        for card in cards:
            property_link = card.css("a.community-card__title::attr(href)").get()
            city_state_zip = card.css(".community-card__city-state::text").get()
            city, state_zip = city_state_zip.split(", ")
            state, zip_code = state_zip.split(" ")
            print(city, state, zip_code)

            print(
                card.css(".community-card__title-link::text").get(),
            )

            yield PropertyItem(
                property_name=card.css(".community-card__title-link::text").get(),
                address=card.css(".community-card__number-street::text").get(),
                city=city,
                state=state,
                postal_code=zip_code,
                template_engine="udr",  # TODO: make configurable
                url=response.urljoin(
                    "/".join([property_link, "apartments-pricing"]).replace("//", "/")
                ),
            )
