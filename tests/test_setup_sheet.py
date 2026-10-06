import csv

from caukin.config import load_suppliers, project_file
from caukin.layout import ITEMS_CORE, QUOTE_FIRST_ROW, QUOTE_LINES
from caukin.setup_sheet import SAMPLE_QUOTE, STARTER_CSV, items_headers, quote_row, quote_values


def starter_rows():
    with project_file(*STARTER_CSV).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_starter_csv_matches_items_layout():
    with project_file(*STARTER_CSV).open(encoding="utf-8") as f:
        header = next(csv.reader(f))
    assert header == items_headers(load_suppliers())
    assert header[:8] == ITEMS_CORE  # Quote formulas use Items!A:H by position


def test_starter_items_are_valid():
    rows = starter_rows()
    codes = [r["item_code"] for r in rows]
    assert len(codes) == len(set(codes)) >= 10
    for r in rows:
        assert float(r["pack_qty"]) > 0
        assert r["canonical_unit"] in {"m", "sheet", "bag", "each"}
        assert r["wickes_url"] or r["bq_url"]
        # A missing supplier URL must be explained
        if not (r["wickes_url"] and r["bq_url"]):
            assert r["notes"], r["item_code"]


def test_sample_quote_uses_starter_codes():
    codes = {r["item_code"] for r in starter_rows()}
    assert {c for c, _ in SAMPLE_QUOTE} <= codes


def test_quote_formulas_reference_own_row():
    row = quote_row(12)
    assert "$A12" in row[1] and "F12" in row[6] and "C12*(1+N(E12))*F12" in row[7]
    assert '"NO PRICE"' in row[5]  # never 0 when there's no valid price
    assert row[0] == row[2] == ""  # item_code and qty left for the user


def test_quote_layout_totals():
    rows = quote_values(sample=True)
    last = QUOTE_FIRST_ROW + QUOTE_LINES - 1
    assert rows[QUOTE_FIRST_ROW - 1][0] == SAMPLE_QUOTE[0][0]
    totals = rows[-3:]
    assert totals[0][9] == f"=SUM(J{QUOTE_FIRST_ROW}:J{last})"
    assert totals[2][8] == "Total inc VAT"


def test_project_files_found_from_working_directory(tmp_path, monkeypatch):
    # In CI the package is installed into site-packages, so repo files must be found via cwd.
    (tmp_path / "suppliers.yaml").write_text(
        "suppliers:\n  - {key: tp, name: Travis Perkins, url_column: tp_url}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert [s.key for s in load_suppliers()] == ["tp"]
