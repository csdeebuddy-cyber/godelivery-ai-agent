"""Rebuild app/data/thai_addresses.json from the address Google Sheet.

Usage (from my-ai-project):  python scripts/import_addresses.py [sheet_id]
The sheet must be readable by link and have the columns: province, district, subdistrict, postcode.
"""

import csv
import io
import json
import sys
import urllib.request
from pathlib import Path

DEFAULT_SHEET_ID = "111TbrsRJVhyBmOrhOZVln68lfmz8DTmZDYwzZMARozI"
OUTPUT = Path(__file__).resolve().parents[1] / "app" / "data" / "thai_addresses.json"


def fetch_rows(sheet_id: str) -> list[list[str]]:
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    with urllib.request.urlopen(url, timeout=60) as response:
        text = response.read().decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text)))[1:]


def build(rows: list[list[str]]) -> list[list[str]]:
    unique: set[tuple[str, str, str, str]] = set()
    for row in rows:
        if len(row) < 4:
            continue
        province, district, subdistrict, postcode = (cell.strip() for cell in row[:4])
        if province and district and subdistrict and postcode.isdigit() and len(postcode) == 5:
            unique.add((postcode, subdistrict, district, province))
    return [list(item) for item in sorted(unique)]


def main() -> None:
    sheet_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SHEET_ID
    rows = build(fetch_rows(sheet_id))
    if len(rows) < 5000:
        raise SystemExit(f"Refusing to overwrite: only {len(rows)} valid rows found.")
    payload = {
        "source": f"Google Sheet {sheet_id}",
        "columns": ["postcode", "subdistrict", "district", "province"],
        "rows": rows,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {len(rows)} addresses to {OUTPUT}")


if __name__ == "__main__":
    main()
