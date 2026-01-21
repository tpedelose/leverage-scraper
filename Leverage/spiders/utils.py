from __future__ import annotations

from urllib.parse import urlparse

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scrapy.http import Response


TEMPLATE_ENGINE_MAP = {
    "udr.com": "udr",
    "besparkliving.com": "bespark",
}

MARKER_MAP = {
    "repli360": ["script[src*='repli360.com']"],
    "udr": ["div.udr-component"],
}


def determine_template_engine(response: Response) -> str | None:
    """
    Determine the template engine used by the property website.
    """

    # 1. Use domain-based mapping
    hostname = urlparse(response.url).hostname
    for domain, engine in TEMPLATE_ENGINE_MAP.items():
        if hostname and domain in hostname:
            return engine

    # 2. Parse the page content for known markers (if needed)
    for engine, markers in MARKER_MAP.items():
        for marker in markers:
            if response.css(marker).get():
                return engine

    return None
