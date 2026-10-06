"""One-time builder for the Google Sheet: tabs, headers, formulas, dropdowns, named ranges.

Safe to re-run: tabs that already exist are left alone.
"""

import csv

import gspread
from gspread.utils import ValueInputOption

from caukin.config import Supplier, project_file
from caukin.howto import HOW_TO_TEXT
from caukin.layout import (
    HOW_TO, ITEMS, ITEMS_CORE, ITEMS_TAIL, PRICES, PRICES_HEADERS, QUOTE, QUOTE_FIRST_ROW,
    QUOTE_LINES, SETTINGS, SETTINGS_ROWS, SHEET_DATETIME_PATTERN, supplier_pack_column,
)

STARTER_CSV = ("data", "starter_items.csv")
QUOTE_HEADERS = ["item_code", "description", "qty", "unit", "waste %", "cheapest unit price (ex VAT)",
                 "cheapest supplier", "materials cost", "markup %", "sell price (ex VAT)"]
GBP = "£#,##0.00"
GBP_PRECISE = "£#,##0.0000"

# "Frame a stud wall": 3.0m long x 2.4m high, studs at 600mm centres, boarded both sides.
SAMPLE_QUOTE = [
    # item_code, qty  (timber qty is linear metres)
    ("TIM-C16-4X2-2.4", 20.4),   # 6 studs x 2.4m + 3.0m head plate + 5 noggins x 0.6m
    ("TIM-C16T-4X2-2.4", 3.0),   # treated sole plate
    ("PB-125-TE", 6),            # 7.2m² per side / 2.88m² per sheet, rounded up, x2 sides
    ("SCR-4X50", 60),
]
SAMPLE_LABOUR = ("Labour: 2 operatives, 1 day", 1, "day", 450, 0)  # description, qty, unit, rate, markup


def items_headers(suppliers: list[Supplier]) -> list[str]:
    cols = list(ITEMS_CORE)
    for s in suppliers:
        cols += [s.url_column, supplier_pack_column(s.key)]
    return cols + ITEMS_TAIL


def quote_row(r: int) -> list[str]:
    a = f"$A{r}"
    look = lambda col: f"VLOOKUP({a},{ITEMS}!$A:$H,{col},FALSE)"
    override = f"IFERROR({look(8)},\"\")"
    fresh = f"{PRICES}!$A:$A,{a},{PRICES}!$H:$H,\"ok\",{PRICES}!$G:$G,\">=\"&cutoff"
    return [
        "",
        f'=IF({a}="","",IFERROR({look(2)},"UNKNOWN ITEM CODE"))',
        "",
        f'=IF({a}="","",IFERROR({look(5)},""))',
        f'=IF({a}="","",IFERROR({look(7)},0))',
        # manual override wins; else lowest fresh 'ok' unit price; never 0 when there's nothing
        f'=IF({a}="","",LET(ov,{override},cutoff,NOW()-STALE_DAYS,'
        f'IF(ISNUMBER(ov),ov,IF(COUNTIFS({fresh})=0,"NO PRICE",MINIFS({PRICES}!$E:$E,{fresh})))))',
        f'=IF({a}="","",IF(ISNUMBER({override}),"Manual",IF(NOT(ISNUMBER(F{r})),"",'
        f'IFERROR(TEXTJOIN(" / ",TRUE,FILTER({PRICES}!$B:$B,{PRICES}!$A:$A={a},{PRICES}!$H:$H="ok",'
        f'{PRICES}!$G:$G>=NOW()-STALE_DAYS,{PRICES}!$E:$E=F{r})),""))))',
        f'=IF(F{r}="NO PRICE","NO PRICE",IF(AND(ISNUMBER(C{r}),ISNUMBER(F{r})),C{r}*(1+N(E{r}))*F{r},""))',
        f'=IF(OR({a}<>"",$B{r}<>""),DEFAULT_MARKUP,"")',
        f'=IF(H{r}="NO PRICE","NO PRICE",IF(ISNUMBER(H{r}),H{r}*(1+N(I{r})),""))',
    ]


def quote_values(sample: bool) -> list[list]:
    first, last = QUOTE_FIRST_ROW, QUOTE_FIRST_ROW + QUOTE_LINES - 1
    rows: list[list] = [
        ["CAUKIN Construct - Quote"],
        ["Job:", "Frame a stud wall (sample)" if sample else ""],
        ["Date:", ""],
        ['="Prices last refreshed: "&LAST_RUN'],
        QUOTE_HEADERS,
    ]
    for r in range(first, last + 1):
        row = quote_row(r)
        i = r - first
        if sample and i < len(SAMPLE_QUOTE):
            row[0], row[2] = SAMPLE_QUOTE[i][0], SAMPLE_QUOTE[i][1]
        elif sample and i == len(SAMPLE_QUOTE):
            desc, qty, unit, rate, markup = SAMPLE_LABOUR
            row[1], row[2], row[3], row[5], row[8] = desc, qty, unit, rate, markup
        rows.append(row)
    t = last + 2
    no_price = f'COUNTIF(J{first}:J{last},"NO PRICE")'
    rows.append([])
    rows.append([f'=IF({no_price}>0,"WARNING: "&{no_price}&" line(s) have NO PRICE - totals are incomplete","")',
                 "", "", "", "", "", "", "", "Total ex VAT", f"=SUM(J{first}:J{last})"])
    rows.append(["", "", "", "", "", "", "", "", '="VAT @ "&TEXT(VAT_RATE,"0%")', f"=J{t}*VAT_RATE"])
    rows.append(["", "", "", "", "", "", "", "", "Total inc VAT", f"=J{t}+J{t + 1}"])
    return rows


def _grid(ws: gspread.Worksheet, r0: int, r1: int, c0: int, c1: int) -> dict:
    """0-based, end-exclusive GridRange."""
    return {"sheetId": ws.id, "startRowIndex": r0, "endRowIndex": r1,
            "startColumnIndex": c0, "endColumnIndex": c1}


def _fmt(ws, r0, r1, c0, c1, pattern=None, kind="NUMBER", bold=None) -> dict:
    fmt, fields = {}, []
    if pattern:
        fmt["numberFormat"] = {"type": kind, "pattern": pattern}
        fields.append("userEnteredFormat.numberFormat")
    if bold is not None:
        fmt["textFormat"] = {"bold": bold}
        fields.append("userEnteredFormat.textFormat.bold")
    return {"repeatCell": {"range": _grid(ws, r0, r1, c0, c1), "cell": {"userEnteredFormat": fmt},
                           "fields": ",".join(fields)}}


def _freeze(ws, rows: int) -> dict:
    return {"updateSheetProperties": {"properties": {"sheetId": ws.id, "gridProperties": {"frozenRowCount": rows}},
                                      "fields": "gridProperties.frozenRowCount"}}


def _load_starter(headers: list[str]) -> list[list[str]]:
    with project_file(*STARTER_CSV).open(encoding="utf-8") as f:
        return [[row.get(h, "") for h in headers] for row in csv.DictReader(f)]


def setup(sh: gspread.Spreadsheet, suppliers: list[Supplier], starter_data: bool = True) -> list[str]:
    log: list[str] = []
    existing = {ws.title: ws for ws in sh.worksheets()}
    created: dict[str, gspread.Worksheet] = {}

    def make(title: str, rows: int, cols: int) -> gspread.Worksheet | None:
        if title in existing:
            log.append(f"'{title}' already exists - left unchanged")
            return None
        created[title] = sh.add_worksheet(title=title, rows=rows, cols=cols)
        log.append(f"created '{title}'")
        return created[title]

    requests: list[dict] = [{"updateSpreadsheetProperties": {
        "properties": {"timeZone": "Europe/London", "locale": "en_GB"}, "fields": "timeZone,locale"}}]

    headers = items_headers(suppliers)
    if ws := make(ITEMS, 500, len(headers)):
        body = [headers] + (_load_starter(headers) if starter_data else [])
        ws.update(body, "A1", value_input_option=ValueInputOption.user_entered)
        requests += [_freeze(ws, 1), _fmt(ws, 0, 1, 0, len(headers), bold=True),
                     _fmt(ws, 1, 500, 6, 7, "0%"), _fmt(ws, 1, 500, 7, 8, GBP_PRECISE)]

    if ws := make(PRICES, 1000, len(PRICES_HEADERS)):
        ws.update([PRICES_HEADERS], "A1")
        requests += [_freeze(ws, 1), _fmt(ws, 0, 1, 0, len(PRICES_HEADERS), bold=True),
                     _fmt(ws, 1, 1000, 2, 4, GBP), _fmt(ws, 1, 1000, 4, 5, GBP_PRECISE),
                     _fmt(ws, 1, 1000, 6, 7, SHEET_DATETIME_PATTERN, "DATE_TIME"),
                     _fmt(ws, 1, 1000, 8, 9, SHEET_DATETIME_PATTERN, "DATE_TIME")]

    if ws := make(SETTINGS, 20, 3):
        ws.update([["Setting", "Value"]] + [[label, value] for label, _, value, _ in SETTINGS_ROWS],
                  "A1", value_input_option=ValueInputOption.user_entered)
        named = {nr["name"] for nr in sh.list_named_ranges()}
        requests += [_fmt(ws, 0, 1, 0, 2, bold=True)]
        for i, (_, name, _, pattern) in enumerate(SETTINGS_ROWS, start=1):
            if name not in named:
                requests.append({"addNamedRange": {"namedRange": {"name": name, "range": _grid(ws, i, i + 1, 1, 2)}}})
            if pattern:
                requests.append(_fmt(ws, i, i + 1, 1, 2, pattern))

    # Named ranges must exist before Quote formulas reference them.
    sh.batch_update({"requests": requests})
    requests = []

    if ws := make(QUOTE, QUOTE_FIRST_ROW + QUOTE_LINES + 5, len(QUOTE_HEADERS)):
        ws.update(quote_values(sample=starter_data), "A1", value_input_option=ValueInputOption.user_entered)
        first, last = QUOTE_FIRST_ROW - 1, QUOTE_FIRST_ROW - 1 + QUOTE_LINES
        tot = last + 1
        requests += [
            _freeze(ws, QUOTE_FIRST_ROW - 1),
            _fmt(ws, 0, 1, 0, 1, bold=True), _fmt(ws, first - 1, first, 0, 10, bold=True),
            _fmt(ws, first, last, 4, 5, "0%"), _fmt(ws, first, last, 8, 9, "0%"),
            _fmt(ws, first, last, 5, 6, GBP_PRECISE), _fmt(ws, first, last, 7, 8, GBP),
            _fmt(ws, first, last, 9, 10, GBP), _fmt(ws, tot, tot + 3, 9, 10, GBP, bold=True),
            _fmt(ws, tot, tot + 3, 8, 9, bold=True),
            {"setDataValidation": {"range": _grid(ws, first, last, 0, 1), "rule": {
                "condition": {"type": "ONE_OF_RANGE", "values": [{"userEnteredValue": f"={ITEMS}!$A$2:$A"}]},
                "showCustomUi": True, "strict": False}}},
        ]

    if ws := make(HOW_TO, len(HOW_TO_TEXT) + 5, 1):
        ws.update([[line] for line in HOW_TO_TEXT], "A1")
        requests += [{"updateDimensionProperties": {
            "range": {"sheetId": ws.id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 900}, "fields": "pixelSize"}}]

    # Drop the blank default tab a new spreadsheet comes with.
    for title in ("Sheet1", "Sheet 1"):
        if title in existing and not any(existing[title].get_all_values()):
            requests.append({"deleteSheet": {"sheetId": existing[title].id}})
            log.append(f"removed empty '{title}'")

    if requests:
        sh.batch_update({"requests": requests})
    return log
