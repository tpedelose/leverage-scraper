from __future__ import annotations

import psycopg
import scrapy
from psycopg.rows import dict_row
from urlmatch import urlmatch
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scrapy.crawler import Crawler
    from playwright.async_api import Route


class DatabaseSpider(scrapy.Spider):
    """
    A spider that connects to a database to retrieve start URLs.
    """

    COMPANY_ID: int  # To be defined in subclasses

    @classmethod
    def from_crawler(cls, crawler: Crawler, *args, **kwargs) -> DatabaseSpider:
        db_dsn: str = crawler.settings.get("DB_DSN")

        # cls.logger.info(f"DatabaseSpider connecting to DB with DSN: {db_dsn}")
        with psycopg.connect(db_dsn) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                # Get property URLs to scrape
                # TODO: Either rename this class or make it more generic
                # TODO: Only select those that are designated for scraping
                sql = "SELECT * FROM properties WHERE company_id=%(company_id)s"
                cur.execute(
                    sql,
                    {
                        "company_id": cls.COMPANY_ID,
                    },
                )
                properties = cur.fetchall()

                start_urls = []
                for entry in properties:
                    url = entry.get("url")
                    if url:
                        start_urls.append(url)

                kwargs["start_urls"] = start_urls

        return super().from_crawler(crawler, *args, **kwargs)


class ContentBlockerSpider(scrapy.Spider):
    """
    A spider that uses ad-blocking techniques to optimize page loading.
    """

    blocked_resource_types: set[str] = set()
    blocked_domains: set[str] = set()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        blocklists = kwargs.get("blocklists", [])
        for blocklist in blocklists:
            try:
                with open(blocklist, "r") as f:
                    for line in f:
                        domain = line.strip()
                        if domain and not domain.startswith("#"):
                            self.blocked_domains.add(domain)
            except Exception as e:
                self.logger.error(f"Error reading domain file {blocklist}: {e}")

    async def route_handler(self, route: Route) -> None:
        # Block fonts, images, and media to speed up loading
        if route.request.resource_type in self.blocked_resource_types:
            await route.abort()

        # Block known ad/tracker domains
        # TODO: Optimize this checks
        elif any(
            urlmatch(pattern, route.request.url) for pattern in self.blocked_domains
        ):
            await route.abort()

        else:
            await route.continue_()
