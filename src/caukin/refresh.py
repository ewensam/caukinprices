"""Refresh logic: scrape every configured item/supplier URL and rebuild the Prices table.

Pure functions over plain dicts so it can be tested without Google Sheets.
"""

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from itertools import zip_longest

from caukin.config import Supplier
from caukin.layout import DATETIME_FORMAT, PRICES_HEADERS, supplier_pack_column
from caukin.pricing import ex_vat, unit_price
from caukin.scrape import ScrapeError, ScrapeResult

log = logging.getLogger(__name__)

Scraper = Callable[[str, Supplier], ScrapeResult]


@dataclass
class Job:
    item_code: str
    supplier: Supplier
    url: str
    pack_qty: float | None
    error: str | None = None  # set when the Items row is unusable


@dataclass
class RunSummary:
    ok: int = 0
    failed: int = 0
    failures: list[str] = field(default_factory=list)

    def text(self, now: datetime) -> str:
        s = f"{now.strftime('%Y-%m-%d %H:%M')} - {self.ok} ok, {self.failed} failed"
        return s + (" (see Prices tab)" if self.failed else "")


def _num(value: str) -> float | None:
    try:
        return float(str(value).replace(",", "").replace("£", "").strip())
    except ValueError:
        return None


def _parse_dt(value: str) -> datetime | None:
    try:
        return datetime.strptime(value.strip(), DATETIME_FORMAT)
    except (ValueError, AttributeError):
        return None


def build_jobs(items: list[dict[str, str]], suppliers: list[Supplier]) -> list[Job]:
    jobs = []
    for row in items:
        code = row.get("item_code", "").strip()
        if not code:
            continue
        for s in suppliers:
            url = row.get(s.url_column, "").strip()
            if not url:
                continue
            raw_qty = row.get(supplier_pack_column(s.key), "").strip() or row.get("pack_qty", "")
            qty = _num(raw_qty)
            err = None if qty and qty > 0 else "pack_qty missing or not a positive number on Items tab"
            jobs.append(Job(code, s, url, qty, err))
    return jobs


def interleave(jobs: list[Job]) -> list[Job]:
    """Round-robin across suppliers so per-supplier delays overlap."""
    by_supplier: dict[str, list[Job]] = {}
    for j in jobs:
        by_supplier.setdefault(j.supplier.key, []).append(j)
    return [j for group in zip_longest(*by_supplier.values()) for j in group if j]


class Throttle:
    """Keep a random 3-5s (per supplier config) gap between requests to the same supplier."""

    def __init__(self, sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic):
        self.sleep, self.clock = sleep, clock
        self.last: dict[str, float] = {}

    def wait(self, supplier: Supplier) -> None:
        if supplier.key in self.last:
            gap = random.uniform(*supplier.delay_seconds)
            remaining = self.last[supplier.key] + gap - self.clock()
            if remaining > 0:
                self.sleep(remaining)
        self.last[supplier.key] = self.clock()


def run_refresh(
    items: list[dict[str, str]],
    prices: list[dict[str, str]],
    suppliers: list[Supplier],
    vat_rate: float,
    stale_days: float,
    scraper: Scraper,
    now: Callable[[], datetime] = datetime.now,
    throttle: Throttle | None = None,
) -> tuple[list[dict[str, str]], RunSummary]:
    """Return the new Prices table (one row per item/supplier) and a run summary."""
    throttle = throttle or Throttle()
    existing = {(r.get("item_code", ""), r.get("supplier", "")): r for r in prices}
    summary = RunSummary()
    out: dict[tuple[str, str], dict[str, str]] = {}

    for job in interleave(build_jobs(items, suppliers)):
        key = (job.item_code, job.supplier.name)
        row = {h: "" for h in PRICES_HEADERS} | existing.get(key, {})
        row.update(item_code=job.item_code, supplier=job.supplier.name, url=job.url)

        error = job.error
        result = None
        if error is None:
            throttle.wait(job.supplier)
            try:
                result = scraper(job.url, job.supplier)
            except ScrapeError as e:
                error = str(e)
            except Exception as e:  # never let one bad page kill the run
                log.exception("unexpected error scraping %s", job.url)
                error = f"unexpected error: {e.__class__.__name__}"

        stamp = now().strftime(DATETIME_FORMAT)
        row["last_attempt_at"] = stamp
        if result is not None:
            p_ex = ex_vat(result.price, vat_rate, job.supplier.prices_include_vat)
            row.update(
                raw_price_inc_vat=f"{result.price:.2f}",
                price_ex_vat=str(round(p_ex, 6)),
                unit_price_ex_vat=str(round(unit_price(p_ex, job.pack_qty), 6)),
                product_title_found=result.title,
                fetched_at=stamp,
                status="ok",
                error="",
            )
            summary.ok += 1
        else:
            # Keep the last good price for reference, but it no longer counts as current.
            row["status"] = "stale" if row.get("raw_price_inc_vat") else "failed"
            row["error"] = error or "unknown error"
            summary.failed += 1
            summary.failures.append(f"{job.item_code} @ {job.supplier.name}: {row['error']}")
            log.warning("FAILED %s @ %s: %s", job.item_code, job.supplier.name, row["error"])
        out[key] = row

    # Safety net: anything marked ok but older than the threshold is stale.
    cutoff = now() - timedelta(days=stale_days)
    for row in out.values():
        fetched = _parse_dt(row.get("fetched_at", ""))
        if row["status"] == "ok" and (fetched is None or fetched < cutoff):
            row["status"] = "stale"

    # Rows whose item/URL was removed from Items are dropped, so Prices mirrors Items.
    return sorted(out.values(), key=lambda r: (r["item_code"], r["supplier"])), summary
