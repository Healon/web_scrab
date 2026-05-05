import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from price_report import PriceScraper


@pytest.fixture()
def scraper():
    return PriceScraper()


def test_pchome_price_prefers_low_over_p_and_m(scraper):
    product = {
        "Price": {
            "M": 8990,
            "P": 5149,
            "Low": 4599,
        }
    }

    assert scraper._pchome_price(product) == 4599


def test_pchome_price_falls_back_to_p_when_low_missing(scraper):
    product = {
        "Price": {
            "M": 8990,
            "P": 5149,
        }
    }

    assert scraper._pchome_price(product) == 5149


def test_pchome_price_falls_back_to_m_when_only_list_price_exists(scraper):
    product = {
        "Price": {
            "M": 8990,
        }
    }

    assert scraper._pchome_price(product) == 8990


def test_pchome_scrape_ignores_query_string_when_building_api_url(scraper, monkeypatch):
    captured = {}

    def fake_get_json(api_url, referer=None):
        captured["api_url"] = api_url
        return [{"Price": {"Low": 474, "P": 5149, "M": 8990}, "Nick": "test"}]

    monkeypatch.setattr(scraper, "_get_json", fake_get_json)

    scraper._scrape_pchome("https://24h.pchome.com.tw/prod/DBDF0C-1900J14FM?fq=/S/DBDF0C")

    assert "id=DBDF0C-1900J14FM" in captured["api_url"]
    assert "fq=" not in captured["api_url"]
