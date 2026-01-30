from __future__ import annotations

import re
from email.utils import parsedate_to_datetime
from datetime import datetime
from pathlib import Path
from scrapy import Spider, Request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scrapy.http import Response


regex_patterns: dict = {
    "phone": r"(\+\d{1,2}\s?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}",
    "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
}
for key, pattern in regex_patterns.items():
    regex_patterns[key] = re.compile(pattern)


class IndexerSpider(Spider):
    """
    Base class for property indexer spiders.
    """

    # TODO? Grab start_urls from database instead of hardcoding?

    company_name: str

    async def start(self):
        for url in self.start_urls:
            yield Request(url=url)

    def save_page(self, response: Response) -> None:
        header_date = response.headers.get("Date", None)
        if header_date is not None:
            timestamp = parsedate_to_datetime(header_date.decode("utf-8"))
        else:
            self.logger.warning("No Date header found in response.")
            timestamp = datetime.now()

        filename = Path(f"output/{self.name}_{timestamp.isoformat()}.html")
        self.logger.debug(f"Saving page content to {filename}.")
        filename.parent.mkdir(parents=True, exist_ok=True)
        filename.write_bytes(response.body)

    def parse(self, response: Response):
        raise NotImplementedError("Subclasses must implement the parse method.")
