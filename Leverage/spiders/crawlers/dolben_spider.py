from Leverage.spiders.repli360_spider import Repli360Spider
from Leverage.spiders.spider import DatabaseSpider


class DolbenSpider(DatabaseSpider, Repli360Spider):
    """
    Spider to scrape apartment listings from Dolben properties.
    """

    name: str = "dolben"

    blocked_domains = set(
        [
            "*://leads.multihub.io/*",
            "*://rtc.multiscreensite.com/*",
            "*://*.betterbot.ai/*",
            "*://*.woorank.com/*",
        ]
    )

    COMPANY_ID = 1  # Company ID in DB
