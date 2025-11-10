import pytest
import scrapy
from Leverage.Leverage.spiders.repli360_spider import Repli360Spider

def test_parse_apartment_listings_basic():
    spider = Repli360Spider()
    sample_html = """
    <table id="fp_table1">
      <tr class="unitlisting">
        <td><div class="unitNumber">101</div></td>
        <td>$1,200</td>
        <td>$500</td>
        <td>2025-12-01</td>
        <td><a id="goto_lease_1" href="/lease?BuildingID=2&Term=12">Lease</a></td>
      </tr>
    </table>
    """
    selector = scrapy.Selector(text=sample_html)
    results = list(spider.parse_apartment_listings(selector))
    assert len(results) == 1
    r = results[0]
    assert r['unit_number'] == '101'
    assert r['rent'] == '1200'
    assert r['deposit'] == '500'
    assert r['date_available'] == '2025-12-01'
    assert r['building_id'] == '2'
    assert r['lease_term'] == '12'