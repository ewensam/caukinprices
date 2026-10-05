"""Google Sheets I/O via a service account."""

import json
import os

import gspread
from gspread.utils import DateTimeOption, ValueInputOption, ValueRenderOption

from caukin.layout import PRICES, PRICES_HEADERS, SETTINGS_ROWS


def connect(sheet_id: str | None = None) -> gspread.Spreadsheet:
    """Credentials come from GOOGLE_SERVICE_ACCOUNT_JSON (the JSON itself, as in GitHub
    Secrets) or GOOGLE_APPLICATION_CREDENTIALS (a path to the key file, handy locally)."""
    sheet_id = sheet_id or os.environ.get("SHEET_ID")
    if not sheet_id:
        raise SystemExit("SHEET_ID is not set")
    if raw := os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"):
        gc = gspread.service_account_from_dict(json.loads(raw))
    elif path := os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        gc = gspread.service_account(filename=path)
    else:
        raise SystemExit("Set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_APPLICATION_CREDENTIALS")
    return gc.open_by_key(sheet_id)


def read_table(ws: gspread.Worksheet) -> list[dict[str, str]]:
    """Rows as dicts keyed by the header row; blank rows skipped."""
    # Raw numbers (so £ formatting doesn't round-trip), but dates as text in the sheet's
    # yyyy-mm-dd hh:mm:ss format rather than serial numbers.
    values = ws.get_all_values(value_render_option=ValueRenderOption.unformatted,
                               date_time_render_option=DateTimeOption.formatted_string)
    if not values:
        return []
    headers = [str(h).strip() for h in values[0]]
    rows = [[str(c) for c in row] for row in values[1:]]
    return [dict(zip(headers, row)) for row in rows if any(c.strip() for c in row)]


def read_settings(sh: gspread.Spreadsheet) -> dict[str, str]:
    ranges = [name for _, name, _, _ in SETTINGS_ROWS]
    resp = sh.values_batch_get(ranges, params={"valueRenderOption": "UNFORMATTED_VALUE"})
    out = {}
    for name, vr in zip(ranges, resp["valueRanges"]):
        vals = vr.get("values") or [[""]]
        out[name] = vals[0][0] if vals[0] else ""
    return out


TEXT_COLUMNS = {"product_title_found", "error", "url", "supplier", "item_code"}


def _cell(header: str, value: str) -> str:
    # Written USER_ENTERED so numbers/dates parse; stop scraped text being read as a formula.
    if header in TEXT_COLUMNS and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def write_prices(sh: gspread.Spreadsheet, rows: list[dict[str, str]]) -> None:
    ws = sh.worksheet(PRICES)
    table = [PRICES_HEADERS] + [[_cell(h, r.get(h, "")) for h in PRICES_HEADERS] for r in rows]
    ws.batch_clear([f"A2:{gspread.utils.rowcol_to_a1(ws.row_count, len(PRICES_HEADERS))}"])
    ws.update(table, "A1", value_input_option=ValueInputOption.user_entered)


def write_last_run(sh: gspread.Spreadsheet, text: str) -> None:
    sh.values_update("LAST_RUN", params={"valueInputOption": "RAW"}, body={"values": [[text]]})
