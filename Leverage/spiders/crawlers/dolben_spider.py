from Leverage.spiders.crawlers import DatabaseSpider
from Leverage.spiders.crawlers.repli360_spider import Repli360Spider


class DolbenSpider(DatabaseSpider, Repli360Spider):
    """
    Spider to scrape apartment listings from Dolben properties.
    """

    name: str = "dolben"
    company_id: int = 1  # Company ID in DB

    blocked_domains = set(
        [
            "*://leads.multihub.io/*",
            "*://rtc.multiscreensite.com/*",
            "*://*.betterbot.ai/*",
            "*://*.woorank.com/*",
        ]
    )
