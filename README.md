# CAUKIN prices

A materials price bank and quoting tool for CAUKIN Construct. It runs on a Google Sheet holding a curated list of materials. A **Prices > Refresh prices** menu fetches current retail prices from Wickes and B&Q and picks the cheapest like-for-like price per unit, and the Quote tab uses those prices.

```
Google Sheet ──(Prices > Refresh prices)──▶ Apps Script ──repository_dispatch──▶ GitHub Actions
     ▲                                                                              │
     └──────────── Google Sheets API (service account) ◀── Python scraper ◀─────────┘
```

Zero hosting cost: the sheet is free, and GitHub Actions free minutes easily cover a 2-minute run.

## The sheet

| Tab | What it's for |
|---|---|
| **Items** | Your curated materials. Columns A–H are fixed. Supplier URL and pack-size columns sit to the right. |
| **Prices** | Written by the refresh, one row per item × supplier (upserted, never appended). Don't edit. |
| **Quote** | Pick an item from the dropdown, enter a qty, and the cheapest valid supplier and price fill in. Free-text rows cover labour and extras. Totals ex VAT, VAT and inc VAT are at the bottom. |
| **Settings** | VAT rate, stale threshold (days), default markup, last run summary. |
| **How To** | Plain-English instructions for day-to-day use. |

### Price rules
- `price_ex_vat = inc_vat / (1 + VAT)` and `unit_price = price_ex_vat / pack_qty`.
- Units: timber per linear metre (`pack_qty` = length, e.g. 2.4), sheet goods per sheet, bagged goods per bag, fixings each.
- If a supplier sells a different pack size (e.g. 100 screws vs 200), set `<supplier>_pack_qty` on that row.
- **Cheapest** = the lowest `unit_price_ex_vat` with `status = ok` and `fetched_at` within the stale threshold. Ties show both suppliers.
- A filled-in `manual_override_price` (ex VAT, per unit) always wins and shows as "Manual".
- With no valid price, Quote shows **NO PRICE**, never 0, and a warning appears above the totals.

### Statuses on the Prices tab
- `ok`: fetched successfully on the latest run.
- `stale`: the latest fetch failed. The last good price is kept for reference but **not used** in quotes. The `error` column says why.
- `failed`: the fetch failed and there's no previous price.

## How the scraper works
1. Plain HTTP GET with a normal browser user agent, then parse the page's JSON-LD `Product`/`Offer` data. Both Wickes and B&Q work this way today.
2. If there's no JSON-LD, fall back to headless Chromium (Playwright) and the CSS selectors in `suppliers.yaml`.
3. The product title is saved with the price so you can check the spec.
4. **B&Q marketplace listings are rejected.** Lots of diy.com products are sold by third-party sellers at odd prices. Only offers sold by B&Q itself count (`allowed_sellers` in `suppliers.yaml`). Listings marked SoldOut or Discontinued are rejected as well, because B&Q leaves old prices up on dead products.
5. It's polite: there's a random 3–5s pause between requests to the same supplier (suppliers are interleaved, so a run still takes about a minute). It never logs in and never tries to get past CAPTCHAs or bot protection. If a site blocks it, that row is marked and the run moves on.

## Starter items

There are 11 items in [`data/starter_items.csv`](data/starter_items.csv), each checked against the live sites in October 2026. Wherever a supplier has no true match, its URL is left blank and the `notes` column says why. Things that differ from the original wish-list:
- **C24 4x2:** neither supplier sells its own C24 in 47x100/45x95 (B&Q's is marketplace-only and labelled "C16/C24"). The items use **C16**, which is standard for stud walls, in untreated (2.4m, both suppliers) and treated (2.4m and 4.8m, Wickes only) versions.
- **Batten 25x38:** Wickes only sells 3.6m, so the spec is 3.6m. B&Q's own 4.8m batten is sold out.
- **Structural ply:** the B&Q sheet doesn't state CE2+, so it's not matched. See the note on that row.

## One-time setup (no programming needed)

Takes about 30 minutes. You need a Google account and a GitHub account.

### 1. Put the code on GitHub
Create a new repository on GitHub (private is fine) and upload this project to it. Note its name in the form `owner/repo`, e.g. `caukin/caukinprices`.

### 2. Create the Google Sheet
1. Go to sheets.google.com and create a **blank** spreadsheet. Name it e.g. "CAUKIN Prices".
2. Copy the **sheet ID** from the address bar: it's the long code between `/d/` and `/edit`.

### 3. Create a Google "service account" (the robot that writes prices)
1. Go to console.cloud.google.com and create a project (e.g. "caukin-prices").
2. Search for **Google Sheets API** and click **Enable**.
3. Go to **IAM & Admin > Service Accounts > Create service account**. Name it "price-bot" and click **Done**. It needs no roles.
4. Click the new service account, open **Keys > Add key > Create new key > JSON**, and a `.json` file downloads. **Treat it like a password.** Don't email it or put it in the repo.
5. Copy the service account's email address (it looks like `price-bot@caukin-prices.iam.gserviceaccount.com`).

### 4. Share the sheet with the robot
In the Google Sheet, click **Share**, paste the service account email, give it **Editor** access, and untick "Notify".

### 5. Add the secrets to GitHub
In the GitHub repo, go to **Settings > Secrets and variables > Actions > New repository secret** and add two secrets:
- `GOOGLE_SERVICE_ACCOUNT_JSON`: open the downloaded `.json` file in Notepad, copy **all** of it, and paste it in.
- `SHEET_ID`: the sheet ID from step 2.

Then delete the `.json` file from your Downloads folder.

### 6. Build the sheet's tabs
In the GitHub repo, go to **Actions > "Set up sheet (one-time)" > Run workflow**. After about a minute, the sheet has the Items, Prices, Quote, Settings and How To tabs, loaded with the starter items and a sample "frame a stud wall" quote. Re-running is safe: tabs that already exist are left alone.

### 7. Create a GitHub token for the button
1. On GitHub, go to your profile picture > **Settings > Developer settings > Personal access tokens > Fine-grained tokens > Generate new token**.
2. Name it "caukin sheet button". Set an expiry (up to a year) and **put a reminder in your calendar to renew it**.
3. Under **Repository access**, choose **Only select repositories** and pick this repo.
4. Under **Permissions > Repository permissions**, set **Contents** to **Read and write**. Nothing else is needed.
5. Click **Generate** and copy the token. It starts `github_pat_`.

### 8. Add the menu to the sheet
1. In the Google Sheet, go to **Extensions > Apps Script**.
2. Delete what's in the editor, paste in everything from [`apps_script/Code.gs`](apps_script/Code.gs), and click **Save**. Use the **copy button** at the top right of the file on GitHub rather than selecting text by hand. A line cut short during the paste gives errors like `Cannot read properties of undefined (reading 'getProperty')`.
3. Click the **cog (Project Settings)**, scroll to **Script Properties**, and add:
   - `GITHUB_TOKEN`: the token from step 7.
   - `GITHUB_REPO`: `owner/repo` from step 1.
4. Close the Apps Script tab and reload the sheet. After a few seconds a **Prices** menu appears in the top menu bar, to the right of **Help**.
5. Click **Prices > Refresh prices**. The first time, Google asks you to authorise the script: click **Advanced > Go to (project) > Allow**. This is your own script.

### 9. Check it works
After about 2 minutes:
- **Settings > Last run** reads something like `2026-10-05 20:38 - 17 ok, 0 failed`.
- **Prices** shows every row with a timestamp.
- **Quote** shows the stud-wall sample with a supplier and price on each line.

If nothing happens, look at **Actions** in GitHub. Each run's log lists every failure and its reason.

## Maintenance
- **The GitHub token expires** (set in step 7). When it does, the button shows "GitHub refused the request (HTTP 401)". Generate a new token the same way and replace `GITHUB_TOKEN` in Script Properties.
- If GitHub Actions is slow to start, check githubstatus.com: runner delays there are outside this project's control.

## Adding a new item
Follow **How To** in the sheet. In short: write a precise spec, find the matching product page at each supplier (for B&Q, make sure it's sold by B&Q), paste the URLs, and set `canonical_unit` and `pack_qty`. If a supplier has no true match, leave its URL blank and say why in `notes`.

To check a URL before adding it (needs Python, see Development below):
```
caukin check-url bq https://www.diy.com/departments/...
```

## Adding a new supplier (e.g. Travis Perkins, MKM)
1. Add an entry to `suppliers.yaml` with a `key`, `name`, `url_column` and, if needed, `allowed_sellers` and `selectors`.
2. On the Items tab, add two columns to the right with headers that exactly match `url_column` (e.g. `tp_url`) and `<key>_pack_qty` (e.g. `tp_pack_qty`).
3. Check a couple of URLs with `caukin check-url tp <url>`. If it reports "no JSON-LD price", the site needs the browser fallback: install the extra with `pip install -e ".[browser]"` and `playwright install chromium`, then set the CSS `selectors.price` in `suppliers.yaml`.
4. Note that trade sites often show trade prices only after login. This tool doesn't log in, so use public retail pages only.

## Development
```
python -m venv .venv
.venv\Scripts\activate          # Windows; use source .venv/bin/activate on Mac/Linux
pip install -e ".[dev]"
pytest                          # offline tests using saved page fixtures
caukin preview                  # live dry run of the starter items; no Google Sheet needed
```
To run against a real sheet locally, set `SHEET_ID` and `GOOGLE_APPLICATION_CREDENTIALS=path\to\key.json`, then run `caukin refresh` or `caukin setup-sheet`.

### Commands
| Command | What it does |
|---|---|
| `caukin refresh` | Scrape every Items URL and rewrite the Prices tab (this is what the button runs). |
| `caukin preview [--csv FILE]` | The same scrape from a CSV, printed to the terminal. Doesn't touch the sheet. |
| `caukin check-url SUPPLIER URL` | Test a single product page. |
| `caukin setup-sheet [--empty]` | Build the tabs in a blank sheet. |

### Layout
```
suppliers.yaml           supplier config
data/starter_items.csv   starter Items rows (verified URLs + notes)
src/caukin/scrape.py     JSON-LD parser + Playwright fallback
src/caukin/refresh.py    refresh logic (pure, unit-tested)
src/caukin/sheets.py     Google Sheets I/O
src/caukin/setup_sheet.py  builds tabs/formulas; Quote formulas live here
apps_script/Code.gs      sheet menu -> GitHub repository_dispatch
.github/workflows/       refresh, one-time setup, tests
```
