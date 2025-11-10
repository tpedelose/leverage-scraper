# leverage-scraper

Web scraper for rent websites using Scrapy.

## Quick start

1. Setup virtualenv with `uv`
```bash
uv sync
```

2. Install Playwright browsers
```bash
uv run python -m playwright install firefox
```

## Run a Scraper

Run a spider with Scrapy (example output to JSON):
```bash
uv run scrapy crawl xyz_spider -o output/xyz_spider.json
```

Note: `scrapy-playwright` spiders require Playwright browsers installed (see above).

## Run tests

Run the whole test suite:
```bash
# or via 'uv' if you use it
uv run pytest
```

Run a single test:
```bash
uv run pytest tests/test_xyz_spider.py::test_parse_apartment_listings_basic -q
```
