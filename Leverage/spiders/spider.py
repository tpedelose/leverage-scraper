from __future__ import annotations

import scrapy
from urlmatch import urlmatch

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Route


class DatabaseSpider(scrapy.Spider):
    """
    A spider that connects to a database to retrieve start URLs.
    """

    COMPANY_ID: int  # To be defined in subclasses

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs) -> DatabaseSpider:
        import psycopg2
        from psycopg2.extras import DictCursor

        # Connect to DB
        db_dsn = crawler.settings.get("DB_DSN")
        with psycopg2.connect(db_dsn, cursor_factory=DictCursor) as conn:
            cur: DictCursor = conn.cursor()  # type: ignore[var-annotated]

            # Get property URLs to scrape
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

            # return cls(start_urls)
            return super(DatabaseSpider, cls).from_crawler(
                crawler, start_urls=start_urls, **kwargs
            )


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
