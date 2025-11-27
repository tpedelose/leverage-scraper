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
