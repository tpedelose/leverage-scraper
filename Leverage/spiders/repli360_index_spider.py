import json
import scrapy
import unicodedata
from pathlib import Path
from urllib.parse import urljoin
from Leverage.items import PropertyItem


class Repli360PropertyIndexer(scrapy.Spider):
    """
    Spider to index Repli360 properties from the Repli360 main properties page.
    """

    # TODO? This is really a Dolben-specific spider. Rename? Also, consider adding branching for other sites that don't use Repli360.
    # TODO? Make this configurable
    name: str = "repli360_index"
    start_urls: list[str] = ["https://www.dolben.com/find-a-community/"]

    LOCATION_LINK_SELECTOR = (
        ".community-list article[data-comp='property'] a::attr(href)"
    )

    schemas = {
        "primary": [
            "Apartment",
            "ApartmentComplex",
            "LocalBusiness",
        ],
        "secondary": [
            "WebSite",
        ],
    }

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
                callback=self.parse_property_page,
            )

    def parse_property_page(self, response):
        self.logger.info(f"Parsing property page: {response.url}")
        filename = f"output/{self.name}_property_page.html"
        Path(filename).write_bytes(response.body)

        json_metadata = response.css(
            "script[type='application/ld+json']::text"
        ).getall()

        data = {}
        for meta in json_metadata:
            meta = json.loads(meta)
            schema_types = meta.get("@type")

            # Skip if no matches
            if schema_types is None:
                continue

            if isinstance(schema_types, str):
                schema_types = [schema_types]

            # Find data structure with priority
            if any(schema in self.schemas["primary"] for schema in schema_types):
                data = meta
                break  # Prefer primary schema
            elif any(schema in self.schemas["secondary"] for schema in schema_types):
                data = meta

        # NOTE: Bespark Living may need a different parser
        # TODO: Ignore if no keys at all
        # Ensure all required keys exist
        address = {
            "addressLocality": None,
            "addressRegion": None,
            "postalCode": None,
            "streetAddress": None,
        }
        schema_address = data.get("address", {})
        # Handle possible variations in locality naming
        if schema_address.get("addressLocality") is None:
            schema_address["addressLocality"] = schema_address.get("locality")
        # Only update necessary keys
        address.update({k: v for k, v in schema_address.items() if k in address})

        # Fallback: read footer if missing any values
        if not address or not all(address.values()):
            footer_address = self.parse_footer_address(response)
            # TODO: Merge more intelligently (e.g. only fill in missing fields?)
            address = {**address, **footer_address}

        # TODO: Some properties need more work on gathering state (gather from index page?)

        yield PropertyItem(
            property_name=data.get("name"),
            address=address.get("streetAddress"),
            city=address.get("addressLocality"),
            state=address.get("addressRegion"),
            postal_code=address.get("postalCode"),
            # TODO: determine dynamically
            template_engine="repli360",
            # TODO: verify URL correctness (and save path as separate field?)
            url=urljoin(response.url, "/floor-plans/"),
        )

    def parse_footer_address(self, response):
        # TODO! This needs heavy work. There are several edge cases to consider.
        # Edge cases examples:
        # - https://www.radiusbos.com : different footer format
        # - https://www.rivageacton.com/ : multiple addresses, first on single line
        #     - Switching to extracting all text from a parent of rteBlock may solve this
        # - besparkliving.com properties : completely different. Do more research.
        # It may be necessary to find an LLM-based solution to parse arbitrary footer formats.

        # Select second column in footer (containing phone and address)
        footer_col = response.css(
            ".dmFooterResp .dmRespRow .dmRespColsWrapper .dmRespCol:nth-child(2)"
        )

        # TODO: Make more robust by selecting all text in column, even nested
        address_text = footer_col.css(
            ".dmNewParagraph:nth-child(2) .rteBlock::text"
        ).getall()

        # Sometimes there are multiple addresses listed. Take the first couple lines.
        address_text = address_text[0:2]

        # Clean up unicode encoded whitespace characters
        address_text = [unicodedata.normalize("NFKD", x).strip() for x in address_text]

        self.logger.debug(address_text)

        city, state_zip = address_text[1].split(", ")
        state, zip_code = state_zip.split(" ")

        return {
            "streetAddress": address_text[0],
            "addressLocality": city,
            "addressRegion": state,
            "postalCode": zip_code,
        }

    def find_apartment_list_page(self, response):
        # Sites have a specific page for apartment listings, find its URL
        raise NotImplementedError("Method not yet implemented.")
