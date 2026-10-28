"""Thai address lookup used by Fasai to verify sub-district / district / province / postcode.

Data: app/data/thai_addresses.json, built from kongvut/thai-province-data (MIT).
"""

import difflib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "thai_addresses.json"

_PREFIXES = {
    "subdistrict": ("ตำบล", "แขวง", "ต."),
    "district": ("กิ่งอำเภอ", "อำเภอ", "เขต", "อ."),
    "province": ("จังหวัด", "จ."),
}
_PROVINCE_ALIASES = {"กรุงเทพ": "กรุงเทพมหานคร", "กทม": "กรุงเทพมหานคร", "กรุงเทพฯ": "กรุงเทพมหานคร"}
FUZZY_CUTOFF = 0.85


@lru_cache(maxsize=1)
def _rows() -> tuple[tuple[str, str, str, str], ...]:
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return tuple(tuple(row) for row in payload["rows"])


@lru_cache(maxsize=1)
def _by_postcode() -> dict[str, list[tuple[str, str, str, str]]]:
    index: dict[str, list[tuple[str, str, str, str]]] = {}
    for row in _rows():
        index.setdefault(row[0], []).append(row)
    return index


def normalize_name(text: str, kind: str) -> str:
    value = re.sub(r"\s+", "", text or "").replace("ฯ", "")
    for prefix in _PREFIXES[kind]:
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    if kind == "province":
        value = _PROVINCE_ALIASES.get(value, value)
    return value


def normalize_postcode(text: str) -> str | None:
    digits = re.sub(r"\D", "", text or "")
    return digits if len(digits) == 5 else None


def _matches(wanted: str, actual: str, kind: str) -> bool:
    a, b = normalize_name(wanted, kind), normalize_name(actual, kind)
    if not a or not b:
        return False
    if a == b:
        return True
    return bool(difflib.get_close_matches(a, [b], n=1, cutoff=FUZZY_CUTOFF))


def lookup_postcode(postcode: str) -> dict[str, Any]:
    code = normalize_postcode(postcode)
    if code is None:
        return {"found": False, "error": "รหัสไปรษณีย์ต้องเป็นตัวเลข 5 หลัก"}
    rows = _by_postcode().get(code)
    if not rows:
        return {"found": False, "postcode": code, "error": "ไม่พบรหัสไปรษณีย์นี้ในฐานข้อมูล"}
    areas: dict[tuple[str, str], list[str]] = {}
    for _, subdistrict, district, province in rows:
        areas.setdefault((province, district), []).append(subdistrict)
    return {
        "found": True,
        "postcode": code,
        "areas": [
            {"province": province, "district": district, "subdistricts": sorted(subs)}
            for (province, district), subs in sorted(areas.items())
        ],
    }


def verify_address(subdistrict: str, district: str, province: str, postcode: str) -> dict[str, Any]:
    """Return {"match": True, "address": {...}} or {"match": False, **lookup_postcode(...)}."""
    code = normalize_postcode(postcode)
    if code is not None:
        for _, row_sub, row_district, row_province in _by_postcode().get(code, []):
            if (
                _matches(subdistrict, row_sub, "subdistrict")
                and _matches(district, row_district, "district")
                and _matches(province, row_province, "province")
            ):
                return {
                    "match": True,
                    "address": {
                        "subdistrict": row_sub,
                        "district": row_district,
                        "province": row_province,
                        "postcode": code,
                    },
                }
    return {"match": False, **lookup_postcode(postcode)}
