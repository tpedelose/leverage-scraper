import scrapy
from scrapy.http import Response
from typing import Any, List
from urllib.parse import urlparse


class ConfigurableSpider(scrapy.Spider):
    """
    A customizable spider that can be initialized with a list of start URLs.

    """

    def __init__(self, start_urls: str | List | None = None, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        if start_urls:
            match start_urls:
                case str():
                    self.start_urls = start_urls.split(",")
                case list():
                    self.start_urls = start_urls
                case _:
                    raise ValueError("start_urls must be a string or list of strings")
            self.logger.info(f"Initialized with {len(self.start_urls)} URLs.")


class TemplateDeterminer(scrapy.Spider):
    """
    A spider mixin to determine the template engine used by a property website.
    """

    TEMPLATE_ENGINE_MAP = {
        "udr.com": "udr",
        # Add more mappings as needed
    }

    def determine_template_engine(self, response: Response) -> str | None:
        # 1. Look for manual overrides
        hostname = urlparse(response.url).hostname
        for domain, engine in self.TEMPLATE_ENGINE_MAP.items():
            if hostname and domain in hostname:
                return engine

        # 2. Parse the page content for known markers (if needed)
        # Look for Repli360 script tag
        if response.css("script[src*='repli360.com']").get():
            return "repli360"

        return None
