from datetime import datetime

import pytest

from caukin.config import Supplier
from caukin.refresh import Throttle, interleave, build_jobs, run_refresh
from caukin.scrape import ScrapeError, ScrapeResult

WICKES = Supplier(key="wickes", name="Wickes", url_column="wickes_url")
BQ = Supplier(key="bq", name="B&Q", url_column="bq_url", allowed_sellers=["B&Q"])
NOW = datetime(2026, 10, 5, 12, 0, 0)


def no_wait() -> Throttle:
    return Throttle(sleep=lambda s: None, clock=lambda: 0.0)


def item(code, pack="2.4", wickes="", bq="", **extra):
    return {"item_code": code, "pack_qty": pack, "wickes_url": wickes, "bq_url": bq, **extra}


def fake_scraper(prices: dict[str, float | Exception]):
    def scrape(url, supplier):
        v = prices[url]
        if isinstance(v, Exception):
            raise v
        return ScrapeResult(price=v, title=f"title for {url}")
    return scrape


def refresh(items, prices=(), scraper=None):
    return run_refresh(items, list(prices), [WICKES, BQ], vat_rate=0.2, stale_days=7,
                       scraper=scraper, now=lambda: NOW, throttle=no_wait())


def test_ok_row_normalised_to_ex_vat_unit_price():
    rows, summary = refresh([item("T1", wickes="w1")], scraper=fake_scraper({"w1": 6.75}))
    [r] = rows
    assert r["supplier"] == "Wickes"
    assert r["raw_price_inc_vat"] == "6.75"
    assert float(r["price_ex_vat"]) == pytest.approx(5.625)
    assert float(r["unit_price_ex_vat"]) == pytest.approx(2.34375)
    assert r["status"] == "ok" and r["fetched_at"] == "2026-10-05 12:00:00"
    assert (summary.ok, summary.failed) == (1, 0)


def test_supplier_pack_qty_override():
    items = [item("S1", pack="200", wickes="w", bq="b", bq_pack_qty="100")]
    rows, _ = refresh(items, scraper=fake_scraper({"w": 4.9, "b": 4.66}))
    by_sup = {r["supplier"]: float(r["unit_price_ex_vat"]) for r in rows}
    assert by_sup["Wickes"] == pytest.approx(4.9 / 1.2 / 200, abs=1e-6)
    assert by_sup["B&Q"] == pytest.approx(4.66 / 1.2 / 100, abs=1e-6)


def test_failure_keeps_last_good_price_and_marks_stale():
    previous = [{"item_code": "T1", "supplier": "Wickes", "raw_price_inc_vat": "7.00",
                 "unit_price_ex_vat": "2.43", "fetched_at": "2026-10-01 09:00:00", "status": "ok"}]
    rows, summary = refresh([item("T1", wickes="w1")], previous,
                            fake_scraper({"w1": ScrapeError("blocked (HTTP 403)")}))
    [r] = rows
    assert r["raw_price_inc_vat"] == "7.00"
    assert r["fetched_at"] == "2026-10-01 09:00:00"
    assert r["last_attempt_at"] == "2026-10-05 12:00:00"
    assert (r["status"], r["error"]) == ("stale", "blocked (HTTP 403)")
    assert summary.failures == ["T1 @ Wickes: blocked (HTTP 403)"]


def test_failure_with_no_history_is_failed():
    rows, _ = refresh([item("T1", bq="b1")], scraper=fake_scraper({"b1": ScrapeError("marketplace seller (X)")}))
    assert rows[0]["status"] == "failed"


def test_unexpected_exception_does_not_abort_run():
    rows, summary = refresh([item("A", wickes="w1"), item("B", wickes="w2")],
                            scraper=fake_scraper({"w1": RuntimeError("boom"), "w2": 10.0}))
    assert [r["status"] for r in rows] == ["failed", "ok"]
    assert summary.ok == 1


def test_missing_pack_qty_fails_without_scraping():
    called = []
    rows, _ = refresh([item("T1", pack="", wickes="w1")],
                      scraper=lambda u, s: called.append(u))
    assert not called
    assert "pack_qty" in rows[0]["error"]


def test_upsert_drops_rows_no_longer_in_items():
    previous = [{"item_code": "GONE", "supplier": "Wickes", "status": "ok"},
                {"item_code": "T1", "supplier": "Wickes", "status": "ok"}]
    rows, _ = refresh([item("T1", wickes="w1")], previous, fake_scraper({"w1": 1.2}))
    assert [(r["item_code"], r["supplier"]) for r in rows] == [("T1", "Wickes")]


def test_jobs_interleave_suppliers():
    items = [item("A", wickes="w", bq="b"), item("B", wickes="w2", bq="b2")]
    order = [(j.item_code, j.supplier.key) for j in interleave(build_jobs(items, [WICKES, BQ]))]
    assert order == [("A", "wickes"), ("A", "bq"), ("B", "wickes"), ("B", "bq")]


def test_throttle_waits_between_same_supplier_only():
    t = [0.0]
    slept = []
    th = Throttle(sleep=lambda s: (slept.append(s), t.__setitem__(0, t[0] + s)), clock=lambda: t[0])
    th.wait(WICKES)
    th.wait(BQ)
    assert slept == []
    th.wait(WICKES)
    assert len(slept) == 1 and 3 <= slept[0] <= 5
