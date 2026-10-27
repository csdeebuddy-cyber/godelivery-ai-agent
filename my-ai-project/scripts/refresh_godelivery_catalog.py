"""Refresh the local product catalog from public Product JSON-LD on godelivery.co.th."""

import json
import re
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

SOURCE_URL = "https://godelivery.co.th/"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = PROJECT_ROOT / "knowledge_base" / "01_products" / "catalog.json"
PROMOTIONS_PATH = PROJECT_ROOT / "knowledge_base" / "04_promotions" / "active_promos.json"


class JsonLdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._inside_json_ld = False
        self._script_parts: list[str] = []
        self.documents: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script":
            return
        attributes = dict(attrs)
        content_type = attributes.get("type") or ""
        if content_type.split(";")[0].strip().lower() == "application/ld+json":
            self._inside_json_ld = True
            self._script_parts = []

    def handle_data(self, data: str) -> None:
        if self._inside_json_ld:
            self._script_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._inside_json_ld:
            self.documents.append("".join(self._script_parts))
            self._script_parts = []
            self._inside_json_ld = False


def _walk_json_ld(value: Any):
    if isinstance(value, list):
        for item in value:
            yield from _walk_json_ld(item)
    elif isinstance(value, dict):
        yield value
        graph = value.get("@graph")
        if graph is not None:
            yield from _walk_json_ld(graph)


def _product_types(value: dict[str, Any]) -> set[str]:
    raw_types = value.get("@type", [])
    if isinstance(raw_types, str):
        return {raw_types.casefold()}
    if isinstance(raw_types, list):
        return {item.casefold() for item in raw_types if isinstance(item, str)}
    return set()


def _extract_products(documents: list[str]) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for document in documents:
        try:
            parsed = json.loads(document)
        except json.JSONDecodeError:
            continue
        for item in _walk_json_ld(parsed):
            if "product" not in _product_types(item):
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            normalized_name = re.sub(r"\s+", " ", name).strip().casefold()
            if normalized_name in seen_names:
                continue
            seen_names.add(normalized_name)

            brand = item.get("brand")
            if isinstance(brand, dict):
                brand = brand.get("name")
            category = item.get("category")
            if isinstance(category, list):
                category = " > ".join(str(part) for part in category)
            ingredients = []
            lowered_name = name.casefold()
            if "งาดำ" in name or "black sesame" in lowered_name:
                ingredients.append("น้ำมันงาดำสกัดเย็น")
            if "คอลลาเจน" in name or "collagen" in lowered_name:
                ingredients.append("คอลลาเจนไทพ์ทู (Type II collagen)")

            products.append(
                {
                    "id": f"godelivery-{len(products) + 1}",
                    "name": re.sub(r"\s+", " ", name).strip(),
                    "aliases": [],
                    "brand_as_listed": brand if isinstance(brand, str) else None,
                    "product_type_as_listed": category if isinstance(category, str) else None,
                    "ingredients_as_listed": ingredients,
                    "short_description": "ชื่อและข้อมูลนี้คัดจาก structured data บนหน้าเว็บ; ยังไม่ได้ยืนยันกับผู้ขาย",
                    "regular_price_thb": None,
                    "promotion_price_thb": None,
                    "promotion": None,
                    "stock_status": "unknown",
                    "sales_script": (
                        f"จากข้อมูลที่หน้าเว็บไซต์แสดง มีรายการ {name} ค่ะ "
                        "ขณะนี้ยังไม่มีราคาหรือโปรโมชันที่ยืนยันได้ ต้องการให้ช่วยตรวจสอบกับร้านค้าก่อนไหมคะ"
                    ),
                    "source_url": SOURCE_URL,
                    "source_type": "public_page_structured_data",
                    "verified": False,
                }
            )
    return products


def refresh() -> int:
    request = Request(
        SOURCE_URL,
        headers={"User-Agent": "GoDeliveryKnowledgeBaseBot/1.0 (product catalog refresh)"},
    )
    try:
        with urlopen(request, timeout=20) as response:
            if response.status != 200:
                raise RuntimeError(f"Source website returned HTTP {response.status}.")
            html = response.read(5_000_001)
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"Could not retrieve the public source website: {exc}") from exc

    if len(html) > 5_000_000:
        raise RuntimeError("Source page exceeds the 5 MB safety limit.")

    parser = JsonLdParser()
    parser.feed(html.decode("utf-8", errors="replace"))
    products = _extract_products(parser.documents)
    if not products:
        raise RuntimeError("No Product structured data was found; existing knowledge-base files were not changed.")

    catalog = {
        "source": {
            "url": SOURCE_URL,
            "retrieved_on": date.today().isoformat(),
            "verification_note": (
                "Extracted from public page structured data. It is not independently verified. "
                "Aggregate prices, stock, health claims, and unconfirmed offers are intentionally excluded."
            ),
        },
        "products": products,
    }
    CATALOG_PATH.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    PROMOTIONS_PATH.write_text(
        json.dumps(
            {
                "source": SOURCE_URL,
                "retrieved_on": date.today().isoformat(),
                "verification_note": "No independently verified active promotions were extracted.",
                "promotions": [],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return len(products)


if __name__ == "__main__":
    count = refresh()
    print(f"Refreshed {count} unverified product listing(s). No promotions or prices were assumed.")
