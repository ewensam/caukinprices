Build a prototype materials price-bank + quoting tool for CAUKIN Construct, a 2-person UK construction firm.

GOAL
Google Sheet that holds a curated list of materials, fetches current retail prices from Wickes and B&Q on a button press, picks the cheapest like-for-like price, and feeds a quote sheet.

ARCHITECTURE
- Google Sheet (the UI)
- Apps Script: custom menu "Prices > Refresh prices" that triggers a GitHub Actions workflow via repository_dispatch (GitHub token stored in Script Properties, never in code). Shows a toast "Refresh started, takes ~2 mins".
- GitHub repo: Python scraper run by the workflow, writing results back via Google Sheets API (service account; credentials in GitHub Secrets).
- Suppliers must be configurable (suppliers.yaml) so TP/MKM etc. can be added later.

SHEET TABS
1. Items: item_code, description, category, spec (grade/treatment/dims), pack_qty, canonical_unit, default_waste_pct, one URL column per supplier, manual_override_price.
2. Prices: item_code, supplier, raw_price_inc_vat, price_ex_vat, unit_price_ex_vat, product_title_found, fetched_at, status (ok/stale/failed). Upsert, don't append.
3. Quote: item_code (dropdown from Items), description (auto), qty, canonical_unit (auto), waste % (auto from Items, editable), cheapest unit price, cheapest supplier, materials cost, markup %, sell price. Allow free-text rows for labour/extras. Totals ex-VAT, VAT, inc-VAT at bottom.
4. Settings: VAT rate (20%), stale threshold (7 days), default markup %.
5. How To: plain-English instructions (see DOCS).

PRICE LOGIC
- Normalise: price_ex_vat = inc_vat / (1 + VAT); unit_price = price_ex_vat / pack_qty.
- Units: timber per linear metre; sheet goods per sheet; bagged goods per bag; fixings per unit.
- Cheapest = lowest unit_price where status=ok and fetched_at within stale threshold. manual_override_price wins if filled.
- If no valid price, show "NO PRICE" in Quote, never 0.

SCRAPER
- Per URL: first try plain HTTP + parse JSON-LD Product/Offer schema; fall back to Playwright (headless Chromium) + CSS selector per supplier in suppliers.yaml.
- Capture product title alongside price for spec checking.
- On failure: keep last good price, set status=failed/stale, log reason.
- Polite: 1 request per supplier every 3-5s, realistic user agent, no login, no CAPTCHA/bot-protection bypass. If a site blocks, mark failed and move on.
- Write a run summary to a "Last run" cell (time, ok/failed counts).

STARTER DATA
Find real Wickes and B&Q product URLs matching identical specs for ~10 items, e.g.:
- C24 treated 47x100 (4x2) 2.4m and 4.8m
- C24 treated 47x150 (6x2) 3.6m
- Treated roofing batten 25x38 4.8m
- OSB3 18mm 2440x1220
- Plasterboard 12.5mm 2400x1200
- Structural ply 18mm 2440x1220
- Multi-purpose cement 25kg
- Building sand bulk bag
- Wood screws 4x50 box
Verify specs match across suppliers; if no true match exists, leave that URL blank and note it.

DOCS (How To tab + README)
- Adding a new item: define spec, find matching product page on each supplier, paste URLs, set pack_qty/unit.
- Adding a new supplier.
- One-time setup: service account, sharing the sheet, GitHub token, secrets. Step-by-step for a non-developer.

DONE WHEN
Pressing the button refreshes all 10 items, Prices populates with timestamps, and a sample quote for "frame a stud wall" calculates correctly with cheapest supplier shown per line.

Google Sheets ID - 1oDIYOPLSMAYhksnKB7k4erQouDwuUkG67rzVikfoR-k