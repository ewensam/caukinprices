"""Sheet layout shared by setup-sheet and refresh.

Items columns A-H are fixed (Quote formulas reference them by position).
Supplier URL / pack-qty columns can go anywhere to the right; they're found by header.
"""

ITEMS = "Items"
PRICES = "Prices"
QUOTE = "Quote"
SETTINGS = "Settings"
HOW_TO = "How To"

ITEMS_CORE = [
    "item_code",              # A
    "description",            # B
    "category",               # C
    "spec",                   # D
    "canonical_unit",         # E
    "pack_qty",               # F  canonical units per product listing, e.g. 2.4 for a 2.4m length
    "default_waste_pct",      # G
    "manual_override_price",  # H  ex VAT per canonical unit; beats any scraped price
]
ITEMS_TAIL = ["notes"]

PRICES_HEADERS = [
    "item_code",          # A
    "supplier",           # B
    "raw_price_inc_vat",  # C
    "price_ex_vat",       # D
    "unit_price_ex_vat",  # E
    "product_title_found",# F
    "fetched_at",         # G  time of the last *successful* fetch
    "status",             # H  ok / stale / failed
    "last_attempt_at",    # I
    "error",              # J
    "url",                # K
]

# Settings tab: (label, named range, default value, number format)
SETTINGS_ROWS = [
    ("VAT rate", "VAT_RATE", 0.2, "0%"),
    ("Stale after (days)", "STALE_DAYS", 7, "0"),
    ("Default markup", "DEFAULT_MARKUP", 0.15, "0%"),
    ("Last run", "LAST_RUN", "never", None),
]

DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
SHEET_DATETIME_PATTERN = "yyyy-mm-dd hh:mm:ss"

QUOTE_FIRST_ROW = 6
QUOTE_LINES = 40


def supplier_pack_column(supplier_key: str) -> str:
    return f"{supplier_key}_pack_qty"
