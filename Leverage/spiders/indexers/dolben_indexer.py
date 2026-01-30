from __future__ import annotations

import json
import scrapy
import unicodedata
import usaddress
from pathlib import Path
from Leverage.items import PropertyItem
from Leverage.spiders.utils import determine_template_engine
from Leverage.spiders.indexers import IndexerSpider, regex_patterns

from typing import TYPE_CHECKING, Generator

if TYPE_CHECKING:
    from scrapy.http import Response


class DolbenPropertyIndexer(IndexerSpider):
    """
    Spider to index Repli360 properties from the Repli360 main properties page.
    """

    name: str = "dolben_indexer"
    start_urls: list[str] = ["https://www.dolben.com/find-a-community/"]
    company_name: str = "Dolben"

    def parse(self, response: Response):
        # Save initial page for debugging
        self.save_page(response)

        location_links = response.css(
            ".community-list article[data-comp='property'] a::attr(href)"
        ).getall()
        for link in location_links:
            yield scrapy.Request(
                url=response.urljoin(link),
                callback=self.parse_property_page,
            )

    def _get_schema_data(self, response: Response) -> dict:
        accepted_schemas = [
            # Ordered by priority
            {"Apartment", "ApartmentComplex", "LocalBusiness"},
            {"WebSite"},
        ]

        # Try to extract JSON-LD metadata
        json_ld_data = response.css("script[type='application/ld+json']::text").getall()

        metadata = {}
        for meta in json_ld_data:
            meta = json.loads(meta)
            schema_types = meta.get("@type")

            if schema_types is None:
                continue

            if isinstance(schema_types, str):
                schema_types = [schema_types]

            # Find data structure with priority
            for accepted_schema_set in accepted_schemas:
                if any(schema in accepted_schema_set for schema in schema_types):
                    # TODO: Consider case where multiple primary schemas exist. Should we combine?
                    metadata = meta
                    break  # Accept first matching schema set (highest priority)

        return metadata

    def parse_property_page(
        self, response: Response
    ) -> Generator[PropertyItem, None, None]:
        self.logger.info(f"Parsing property page: {response.url}")

        template_engine = determine_template_engine(response)

        self.logger.info(f"Detected template engine: {template_engine}")
        # TODO: Handle unknown template engines
        if template_engine is None:
            self.logger.warning("Could not determine template engine.")
            return

        # Try to extract schema data
        schema_data = self._get_schema_data(response)

        # TODO: Ignore if no keys at all
        # Ensure all required keys exist
        address_data = {
            "addressLocality": None,
            "addressRegion": None,
            "postalCode": None,
            "streetAddress": None,
        }

        schema_address = schema_data.get("address", {})

        # Handle possible variations in locality naming
        if not address_data.get("addressLocality") and "locality" in address_data:
            address_data["addressLocality"] = address_data.get("locality")

        # Only update necessary keys
        address_data.update(
            {k: v for k, v in schema_address.items() if k in address_data}
        )

        # Fallback: read footer if missing any values
        if not address_data or not all(address_data.values()):
            footer_address = self.parse_footer(response, template_engine)
            # TODO: Merge more intelligently (e.g. only fill in missing fields?)
            address_data = {**address_data, **footer_address}

        match template_engine:
            case "repli360":
                apt_list_url = response.urljoin("floor-plans/")
            case "bespark":
                apt_list_url = response.urljoin(
                    f"{Path(response.url).name}-floor-plans/"
                )
            case _:
                # TODO: Something to handle unknown template engines
                apt_list_url = response.urljoin("floor-plans/")

        # NOTE! Bespark uses RentPress for apartment listings.

        yield PropertyItem(
            company_name=self.company_name,
            property_name=schema_data.get("name"),
            address=address_data.get("streetAddress"),
            city=address_data.get("addressLocality"),
            state=address_data.get("addressRegion"),
            postal_code=address_data.get("postalCode"),
            template_engine=template_engine,
            # TODO: verify URL correctness (and save path as separate field?)
            url=apt_list_url,
        )

    def parse_footer(self, response: Response, template: str) -> dict:
        # NOTE: It may be necessary to find an LLM-based solution to parse arbitrary footer formats.
        match template:
            case "repli360":
                return self.parse_footer_repli360(response)
            case "bespark":
                return self.parse_footer_bespark(response)
            case _:
                raise NotImplementedError(
                    f"Footer parsing not implemented for template: {template}"
                )

    def parse_footer_repli360(self, response: Response) -> dict:
        self.logger.debug("123; Parsing footer address for Repli360 template.")

        # NOTE: assumes address is in second column
        column_text = response.css(
            ".dmFooterResp .dmRespColsWrapper > .dmRespCol:nth-child(2) ::text"
        ).getall()

        # Clean up text (e.g. unicode whitespace) and filter out empty lines
        column_text = [
            unicodedata.normalize("NFKD", line).strip()
            for line in column_text
            if line.strip()
        ]
        # Deduplicate lines while preserving order
        column_text = list(dict.fromkeys(column_text))

        print("Address Text:", column_text)

        # TODO! Return extracted phone and email
        data: dict = {
            "phone": None,
            "email": None,
        }

        # Iterate and check each pattern
        unparsed_column_text = column_text.copy()
        for i, text in enumerate(column_text):
            for key in ["phone", "email"]:
                match = regex_patterns[key].search(text)
                if match:
                    data[key] = match.group()
                    # Remove to avoid interference with address parsing
                    unparsed_column_text.pop(i)
                    break

        # Since the address may be split across multiple lines, try to parse each line and compile
        from collections import OrderedDict

        collected_address = OrderedDict()
        for i, text in enumerate(unparsed_column_text):
            tagged_address, address_type = usaddress.tag(text)
            # Prioritize values that already exist
            for key, value in tagged_address.items():
                if key not in collected_address:
                    collected_address[key] = value

        # Pop off recipient name if exists (not needed, and noisy)
        if "Recipient" in collected_address:
            collected_address.pop("Recipient")

        # TODO? look into normalizing address (with scourgify?)
        street_address_parts = [
            part
            for key, part in collected_address.items()
            if key
            in [
                "AddressNumber",
                "StreetNamePreDirectional",
                "StreetName",
                "StreetNamePostType",
                "StreetNamePostDirectional",
                "OccupancyType",
                "OccupancyIdentifier",
            ]
        ]

        return {
            "streetAddress": " ".join(street_address_parts),
            "addressLocality": collected_address.get("PlaceName"),
            "addressRegion": collected_address.get("StateName"),
            "postalCode": collected_address.get("ZipCode"),
        }

    def parse_footer_bespark(self, response: Response) -> dict:
        # besparkliving.com properties : completely different footer format
        raise NotImplementedError("Method not yet implemented.")

    def find_apartment_list_page(self, response: Response) -> str:
        # Sites have a specific page for apartment listings, find its URL
        raise NotImplementedError("Method not yet implemented.")
