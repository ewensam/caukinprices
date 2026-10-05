"""Fetch a product page and extract its price + title.

Strategy: plain HTTP + JSON-LD Product/Offer first; headless Chromium + CSS
selectors as a fallback. No login, no CAPTCHA or bot-protection bypass — if a
site blocks us we report it and move on.
"""

import html
import json
import re
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

from caukin.config import Supplier

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}
BLOCK_MARKERS = ("access denied", "are you a robot", "verify you are human", "request unsuccessful")


class ScrapeError(Exception):
    """Raised when a price can't be read; the message is written to the sheet."""


@dataclass
class ScrapeResult:
    price: float
    title: str
    seller: str | None = None
    method: str = "jsonld"


def fetch_html(url: str, session: requests.Session | None = None, timeout: float = 20) -> str:
    http = session or requests
    try:
        resp = http.get(url, headers=HEADERS, timeout=timeout)
    except requests.RequestException as e:
        raise ScrapeError(f"network error: {e.__class__.__name__}") from e
    if resp.status_code in (403, 429):
        raise ScrapeError(f"blocked (HTTP {resp.status_code})")
    if resp.status_code == 404:
        raise ScrapeError("page not found (HTTP 404) - product may be discontinued")
    if resp.status_code >= 400:
        raise ScrapeError(f"HTTP {resp.status_code}")
    return resp.text


def _iter_jsonld(soup: BeautifulSoup):
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except json.JSONDecodeError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                yield node
                if "@graph" in node:
                    stack.extend(node["@graph"])


def _is_product(node: dict) -> bool:
    t = node.get("@type")
    return t == "Product" or (isinstance(t, list) and "Product" in t)


def _offer_price(offer: dict) -> float | None:
    raw = offer.get("price", offer.get("lowPrice"))
    if raw is None and isinstance(offer.get("priceSpecification"), dict):
        raw = offer["priceSpecification"].get("price")
    try:
        return float(str(raw).replace(",", "").replace("£", ""))
    except (TypeError, ValueError):
        return None


GONE = {"SoldOut", "Discontinued"}


def _availability(offer: dict) -> str:
    return str(offer.get("availability") or "").rsplit("/", 1)[-1]


def _seller_name(offer: dict) -> str | None:
    seller = offer.get("seller")
    if isinstance(seller, dict):
        return html.unescape(seller.get("name", "")) or None
    if isinstance(seller, str):
        return html.unescape(seller)
    return None


def parse_jsonld(page: str, supplier: Supplier) -> ScrapeResult:
    """Pull the price from a schema.org Product's offers."""
    soup = BeautifulSoup(page, "html.parser")
    product = next((n for n in _iter_jsonld(soup) if _is_product(n)), None)
    if product is None:
        raise ScrapeError("no JSON-LD price")

    title = html.unescape(product.get("name", "")).strip()
    offers = product.get("offers") or []
    if isinstance(offers, dict):
        offers = [offers]

    priced = [o for o in offers if _offer_price(o) is not None]
    if not priced:
        raise ScrapeError("no JSON-LD price")
    # Delisted products often still publish a (stale) price — don't trust it.
    live = [o for o in priced if _availability(o) not in GONE]
    if not live:
        raise ScrapeError("sold out / discontinued")
    candidates = [(_offer_price(o), _seller_name(o)) for o in live]

    if supplier.allowed_sellers:
        allowed = {s.lower() for s in supplier.allowed_sellers}
        # Offers with no seller listed are the retailer's own.
        own = [(p, s) for p, s in candidates if s is None or s.lower() in allowed]
        if not own:
            sellers = sorted({s for _, s in candidates if s})
            raise ScrapeError(f"marketplace seller ({', '.join(sellers)})")
        candidates = own

    price, seller = min(candidates, key=lambda c: c[0])
    return ScrapeResult(price=price, title=title, seller=seller)


def _looks_blocked(page: str) -> bool:
    head = page[:5000].lower()
    return any(m in head for m in BLOCK_MARKERS)


_PRICE_RE = re.compile(r"£\s*([0-9][0-9,]*\.?[0-9]{0,2})")


def fetch_with_browser(url: str, supplier: Supplier, timeout_ms: int = 30000) -> ScrapeResult:
    """Fallback: render the page in headless Chromium and read CSS selectors."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise ScrapeError("no JSON-LD price (browser fallback not installed)") from e
    if not supplier.selectors.price:
        raise ScrapeError("no JSON-LD price and no CSS selector configured")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT, locale="en-GB")
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            content = page.content()
            if _looks_blocked(content):
                raise ScrapeError("blocked by site (browser)")
            # The page may embed JSON-LD after JS runs.
            try:
                result = parse_jsonld(content, supplier)
                result.method = "browser-jsonld"
                return result
            except ScrapeError as e:
                if e.args[0].startswith("marketplace"):
                    raise
            price_el = page.wait_for_selector(supplier.selectors.price, timeout=10000)
            price_text = price_el.inner_text() if price_el else ""
            title = ""
            if supplier.selectors.title and (t := page.query_selector(supplier.selectors.title)):
                title = t.inner_text().strip()
            browser.close()
    except PlaywrightError as e:
        raise ScrapeError(f"browser error: {str(e).splitlines()[0][:120]}") from e

    m = _PRICE_RE.search(price_text)
    if not m:
        raise ScrapeError(f"price selector matched but no £ amount in {price_text[:40]!r}")
    return ScrapeResult(price=float(m.group(1).replace(",", "")), title=title, method="browser-css")


def scrape(url: str, supplier: Supplier, session: requests.Session | None = None,
           use_browser: bool = True) -> ScrapeResult:
    page = fetch_html(url, session)
    if _looks_blocked(page):
        raise ScrapeError("blocked by site")
    try:
        return parse_jsonld(page, supplier)
    except ScrapeError as e:
        if not use_browser or e.args[0].startswith("marketplace"):
            raise
    return fetch_with_browser(url, supplier)
