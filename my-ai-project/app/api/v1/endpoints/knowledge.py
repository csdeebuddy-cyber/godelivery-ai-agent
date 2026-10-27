from fastapi import APIRouter, Body, HTTPException, Query

from app.schemas.knowledge import ProductImportRecord, PromotionImportRecord
from app.services.knowledge_base import (
    get_active_knowledge_base_promotions,
    get_knowledge_base_products,
    get_knowledge_base_status,
    search_knowledge_base,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge-base"])


@router.get("/status")
async def knowledge_status() -> dict:
    try:
        return get_knowledge_base_status()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/products")
async def knowledge_products() -> dict:
    try:
        return get_knowledge_base_products()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/products/preview")
async def preview_product_import(
    products: list[ProductImportRecord] = Body(..., max_length=100),
) -> dict:
    preview_records = []
    for product in products:
        supplied_fields = product.model_fields_set - {"id", "name"}
        preview_records.append(
            {
                "id": product.id,
                "name": product.name,
                "verified": False,
                "excluded_unverified_fields": sorted(supplied_fields),
            }
        )
    return {
        "status": "needs_review",
        "persisted": False,
        "products": preview_records,
        "message": (
            "Product data was validated for the future import flow only. "
            "Unverified category, price, unit, highlights, and voice-script data "
            "were excluded; no knowledge-base files were changed."
        ),
    }


@router.get("/promotions")
async def knowledge_promotions() -> dict:
    try:
        return get_active_knowledge_base_promotions()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/promotions/preview")
async def preview_promotion_import(
    promotions: list[PromotionImportRecord] = Body(..., max_length=100),
) -> dict:
    preview_records = []
    for promotion in promotions:
        supplied_fields = promotion.model_fields_set - {"promo_id", "title"}
        preview_records.append(
            {
                "promo_id": promotion.promo_id,
                "title": promotion.title,
                "verified": False,
                "excluded_unverified_fields": sorted(supplied_fields),
            }
        )
    return {
        "status": "needs_review",
        "persisted": False,
        "promotions": preview_records,
        "message": (
            "Promotion data was validated for the future import flow only. "
            "Product applicability, price, details, shipping, and active status "
            "were excluded until verified; no promotion was activated or saved."
        ),
    }


@router.get("/search")
async def knowledge_search(
    q: str = Query(..., min_length=1, max_length=500),
) -> dict:
    try:
        return search_knowledge_base(q)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
