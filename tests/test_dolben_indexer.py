import scrapy
import pytest
import json
from pathlib import Path
from Leverage.Leverage.spiders.dolben_indexer import DolbenPropertyIndexer

# Load test data from files
DATA_DIR = Path(__file__).parent / "data"


def load_test_cases():
    cases = (DATA_DIR / "test_cases.json").read_text()
    return json.loads(cases)


def load_test_file(filename):
    return (DATA_DIR / filename).read_text(encoding="utf-8")


@pytest.mark.parametrize("sample_html,expected_address", load_test_cases())
def test_parse_footer_repli360():
    # Edge cases examples:
    # - https://www.radiusbos.com : different footer format
    # - https://www.rivageacton.com/ : multiple addresses, first on single line
    #     - Switching to extracting all text from a parent of rteBlock may solve this
    spider = DolbenPropertyIndexer()
    sample_html = """
    <div class="dmFooterContainer">
    """
    raise NotImplementedError("Test not yet implemented.")


def test_parse_footer_bespark():
    # besparkliving.com properties : completely different footer format
    spider = DolbenPropertyIndexer()
    sample_html = """
    """
    raise NotImplementedError("Test not yet implemented.")
