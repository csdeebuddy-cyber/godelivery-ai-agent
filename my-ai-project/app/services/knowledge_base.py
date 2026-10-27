import json
import re
import unicodedata
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_BASE_DIR = PROJECT_ROOT / "knowledge_base"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Knowledge base file could not be loaded: {path.name}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Knowledge base file has an invalid structure: {path.name}")
    return data


def _normalize(value: str) -> str:
    return "".join(
        character
        for character in value.casefold()
        if not character.isspace()
        and not unicodedata.category(character).startswith(("P", "S"))
    )


def search_knowledge_base(query: str) -> dict[str, Any]:
    """Return grounded product, promotion, and policy data matching a customer query."""
    catalog = _read_json(KNOWLEDGE_BASE_DIR / "01_products" / "catalog.json")
    promotions_data = _read_json(KNOWLEDGE_BASE_DIR / "04_promotions" / "active_promos.json")
    query_normalized = _normalize(query)
    product_question_terms = {
        "สินค้า", "ผลิตภัณฑ์", "ราคา", "เท่าไหร่", "โปร", "โปรโมชั่น",
        "ส่วนลด", "ของแถม", "สั่ง", "ซื้อ", "ขาย", "แนะนำ", "มีอะไร",
        "อะไรบ้าง", "งาดำ", "allday", "collagen",
    }

    products = catalog.get("products", [])
    matches: list[dict[str, Any]] = []
    for product in products:
        searchable_values = [
            str(product.get("name", "")),
            str(product.get("brand_as_listed", "")),
            str(product.get("product_type_as_listed", "")),
            *[str(alias) for alias in product.get("aliases", [])],
            *[str(ingredient) for ingredient in product.get("ingredients_as_listed", [])],
        ]
        normalized_values = [_normalize(value) for value in searchable_values]
        matched = any(
            normalized and (normalized in query_normalized or query_normalized in normalized)
            for normalized in normalized_values
        )
        if not matched:
            matched = any(term in query_normalized for term in product_question_terms)
        if matched:
            matches.append(product)

    promotion_terms = ("โปร", "โปรโมชั่น", "ส่วนลด", "ของแถม", "promotion", "discount")
    asks_about_promotions = any(term in query_normalized for term in promotion_terms)
    active_promotions = [
        promo
        for promo in promotions_data.get("promotions", [])
        if promo.get("active") is True
    ]

    policy_text = []
    policy_queries = {
        "สั่ง": ("02_ordering_fulfillment/ordering.md",),
        "ซื้อ": ("02_ordering_fulfillment/ordering.md",),
        "ส่ง": ("02_ordering_fulfillment/shipping_returns.md",),
        "จัดส่ง": ("02_ordering_fulfillment/shipping_returns.md",),
        "คืน": ("02_ordering_fulfillment/shipping_returns.md",),
        "คืนเงิน": ("02_ordering_fulfillment/shipping_returns.md",),
        "privacy": ("03_policies/privacy_policy.md",),
        "ข้อมูลส่วนตัว": ("03_policies/privacy_policy.md",),
        "เงื่อนไข": ("03_policies/terms_of_service.md",),
        "ข้อตกลง": ("03_policies/terms_of_service.md",),
    }
    relevant_paths = {
        path
        for term, paths in policy_queries.items()
        if term in query_normalized
        for path in paths
    }
    for relative_path in sorted(relevant_paths):
        path = KNOWLEDGE_BASE_DIR / relative_path
        try:
            policy_text.append({"source": relative_path, "content": path.read_text(encoding="utf-8")})
        except OSError as exc:
            raise RuntimeError(f"Knowledge base document could not be loaded: {relative_path}") from exc

    return {
        "query": query,
        "source": catalog.get("source"),
        "products": matches[:3],
        "promotions": active_promotions if asks_about_promotions else [],
        "promotion_status": (
            "No active promotions are verified in the knowledge base."
            if asks_about_promotions and not active_promotions
            else None
        ),
        "policies": policy_text,
        "not_found": not matches and not policy_text and not active_promotions,
    }


def get_knowledge_base_status() -> dict[str, Any]:
    catalog = _read_json(KNOWLEDGE_BASE_DIR / "01_products" / "catalog.json")
    promotions_data = _read_json(KNOWLEDGE_BASE_DIR / "04_promotions" / "active_promos.json")
    products = catalog.get("products", [])
    promotions = promotions_data.get("promotions", [])
    return {
        "status": "ok",
        "products": len(products),
        "verified_products": sum(product.get("verified") is True for product in products),
        "active_promotions": sum(promo.get("active") is True for promo in promotions),
        "source": catalog.get("source"),
    }


def get_knowledge_base_products() -> dict[str, Any]:
    catalog = _read_json(KNOWLEDGE_BASE_DIR / "01_products" / "catalog.json")
    return {
        "source": catalog.get("source"),
        "products": catalog.get("products", []),
    }


def get_active_knowledge_base_promotions() -> dict[str, Any]:
    promotions_data = _read_json(KNOWLEDGE_BASE_DIR / "04_promotions" / "active_promos.json")
    return {
        "source": promotions_data.get("source"),
        "verification_note": promotions_data.get("verification_note"),
        "promotions": [
            promotion
            for promotion in promotions_data.get("promotions", [])
            if promotion.get("active") is True
        ],
    }


def get_knowledge_base_context() -> dict[str, Any]:
    catalog = _read_json(KNOWLEDGE_BASE_DIR / "01_products" / "catalog.json")
    promotions = _read_json(KNOWLEDGE_BASE_DIR / "04_promotions" / "active_promos.json")
    document_paths = (
        "01_products/product_faqs.md",
        "02_ordering_fulfillment/ordering.md",
        "02_ordering_fulfillment/shipping_returns.md",
        "03_policies/privacy_policy.md",
        "03_policies/terms_of_service.md",
        "05_faq_examples/conversation_samples.md",
    )
    documents = []
    for relative_path in document_paths:
        try:
            content = (KNOWLEDGE_BASE_DIR / relative_path).read_text(encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"Knowledge base document could not be loaded: {relative_path}") from exc
        documents.append({"source": relative_path, "content": content})

    product_fields = (
        "id",
        "name",
        "aliases",
        "brand_as_listed",
        "product_type_as_listed",
        "ingredients_as_listed",
        "short_description",
        "regular_price_thb",
        "promotion_price_thb",
        "promotion",
        "stock_status",
        "sales_script",
        "source_url",
        "source_type",
        "verified",
    )
    return {
        "source": catalog.get("source"),
        "products": [
            {field: product.get(field) for field in product_fields}
            for product in catalog.get("products", [])
        ],
        "promotions": promotions.get("promotions", []),
        "promotion_verification_note": promotions.get("verification_note"),
        "documents": documents,
    }
