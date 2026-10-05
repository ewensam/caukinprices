from pathlib import Path

import pytest

from caukin.config import Supplier, load_suppliers
from caukin.scrape import ScrapeError, parse_jsonld

FIXTURES = Path(__file__).parent / "fixtures"
SUPPLIERS = {s.key: s for s in load_suppliers()}


def page(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_wickes_single_offer():
    r = parse_jsonld(page("wickes_178226.html"), SUPPLIERS["wickes"])
    assert r.price == 28.0
    assert "C24" in r.title and "45 x 145 x 3600mm" in r.title


def test_bq_own_sold_offer_has_no_seller():
    r = parse_jsonld(page("bq_35720_own.html"), SUPPLIERS["bq"])
    assert r.price == 8.4
    assert r.title == "Blue Circle Mastercrete Grey Cement, 25kg Bag"
    assert r.seller is None


def test_bq_marketplace_offer_rejected():
    with pytest.raises(ScrapeError, match="marketplace seller \\(Materials Market\\)"):
        parse_jsonld(page("bq_1234564001150_marketplace.html"), SUPPLIERS["bq"])


def test_marketplace_allowed_when_supplier_has_no_seller_filter():
    open_bq = SUPPLIERS["bq"].model_copy(update={"allowed_sellers": []})
    r = parse_jsonld(page("bq_1234564001150_marketplace.html"), open_bq)
    assert r.price == 30.12
    assert r.seller == "Materials Market"
    assert '(4" x 2")' in r.title  # HTML entities decoded


def test_sold_out_listing_rejected():
    with pytest.raises(ScrapeError, match="sold out"):
        parse_jsonld(page("bq_888764_soldout.html"), SUPPLIERS["bq"])


def test_page_without_jsonld():
    s = Supplier(key="x", name="X", url_column="x_url")
    with pytest.raises(ScrapeError, match="no JSON-LD price"):
        parse_jsonld("<html><h1>Nothing here</h1></html>", s)


def test_graph_and_aggregate_offer():
    s = Supplier(key="x", name="X", url_column="x_url")
    html = """<script type="application/ld+json">
    {"@graph": [{"@type": "WebPage"},
      {"@type": ["Product"], "name": "Thing",
       "offers": {"@type": "AggregateOffer", "lowPrice": "1,234.50"}}]}
    </script>"""
    r = parse_jsonld(html, s)
    assert (r.price, r.title) == (1234.5, "Thing")
