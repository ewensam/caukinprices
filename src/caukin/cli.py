"""Command-line entry point: `caukin --help`."""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import click
import requests

from caukin.config import load_suppliers
from caukin.layout import ITEMS, PRICES
from caukin.refresh import run_refresh
from caukin.scrape import ScrapeError, scrape

LONDON = ZoneInfo("Europe/London")


def london_now() -> datetime:
    # Naive London time, matching the sheet's timezone so NOW()-based staleness lines up.
    return datetime.now(LONDON).replace(tzinfo=None)


@click.group()
@click.option("-v", "--verbose", is_flag=True)
def main(verbose: bool) -> None:
    """CAUKIN Construct materials price-bank."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, format="%(levelname)s %(message)s")


@main.command("check-url")
@click.argument("supplier_key")
@click.argument("url")
@click.option("--no-browser", is_flag=True, help="Skip the headless-browser fallback.")
def check_url(supplier_key: str, url: str, no_browser: bool) -> None:
    """Scrape one URL and print what was found (handy when adding items)."""
    suppliers = {s.key: s for s in load_suppliers()}
    if supplier_key not in suppliers:
        raise click.BadParameter(f"unknown supplier; choose from {', '.join(suppliers)}")
    try:
        r = scrape(url, suppliers[supplier_key], use_browser=not no_browser)
    except ScrapeError as e:
        click.echo(f"FAILED: {e}")
        raise SystemExit(1)
    click.echo(f"GBP {r.price:.2f} inc VAT | {r.title} | seller={r.seller or '-'} | via {r.method}")


@main.command()
@click.option("--sheet-id", envvar="SHEET_ID", help="Spreadsheet ID (or set SHEET_ID).")
@click.option("--no-browser", is_flag=True, help="Skip the headless-browser fallback.")
def refresh(sheet_id: str | None, no_browser: bool) -> None:
    """Scrape all item URLs and update the Prices tab."""
    from caukin import sheets

    sh = sheets.connect(sheet_id)
    settings = sheets.read_settings(sh)
    vat, stale = float(settings["VAT_RATE"]), float(settings["STALE_DAYS"])
    items = sheets.read_table(sh.worksheet(ITEMS))
    prices = sheets.read_table(sh.worksheet(PRICES))
    session = requests.Session()

    rows, summary = run_refresh(
        items, prices, load_suppliers(), vat, stale,
        scraper=lambda url, s: scrape(url, s, session=session, use_browser=not no_browser),
        now=london_now,
    )
    sheets.write_prices(sh, rows)
    text = summary.text(london_now())
    sheets.write_last_run(sh, text)
    click.echo(text)
    for f in summary.failures:
        click.echo(f"  - {f}")


@main.command()
@click.option("--csv", "csv_path", type=click.Path(exists=True), default=None,
              help="Items CSV (default: data/starter_items.csv).")
@click.option("--vat", default=0.2, show_default=True)
@click.option("--no-browser", is_flag=True)
def preview(csv_path: str | None, vat: float, no_browser: bool) -> None:
    """Dry run: scrape every URL in an Items CSV and print prices. No Google Sheet needed."""
    import csv

    from caukin.setup_sheet import STARTER_CSV

    with open(csv_path or STARTER_CSV, encoding="utf-8") as f:
        items = list(csv.DictReader(f))
    session = requests.Session()
    rows, summary = run_refresh(
        items, [], load_suppliers(), vat, stale_days=7,
        scraper=lambda url, s: scrape(url, s, session=session, use_browser=not no_browser),
        now=london_now,
    )
    for r in rows:
        if r["status"] == "ok":
            detail = f"£{float(r['unit_price_ex_vat']):.4f}/unit ex VAT  ({r['product_title_found']})"
        else:
            detail = r["error"]
        click.echo(f"{r['item_code']:<18} {r['supplier']:<7} {r['status']:<7} {detail}")
    click.echo(summary.text(london_now()))


@main.command("setup-sheet")
@click.option("--sheet-id", envvar="SHEET_ID", help="Spreadsheet ID (or set SHEET_ID).")
@click.option("--empty", is_flag=True, help="Don't load the starter items and sample quote.")
def setup_sheet(sheet_id: str | None, empty: bool) -> None:
    """Build the tabs, formulas and dropdowns in a blank Google Sheet (one-time)."""
    from caukin import sheets
    from caukin.setup_sheet import setup

    for line in setup(sheets.connect(sheet_id), load_suppliers(), starter_data=not empty):
        click.echo(line)
