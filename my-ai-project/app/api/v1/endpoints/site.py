import logging
import re
import secrets
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, HTTPException, Response
from google.api_core.exceptions import GoogleAPIError
from google.auth.exceptions import GoogleAuthError

from app.schemas.site_content import CustomerOrderRequest, MemberRegistrationRequest
from app.services.admin_settings import get_google_sheets_settings
from app.services.google_sheets_customer_data import append_customer_row
from app.services.firebase.storage import get_catalog_image
from app.services.site_content import get_site_content


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/site", tags=["public-site"])
LOCAL_TIMEZONE = ZoneInfo("Asia/Bangkok")
CATALOG_ASSET_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")


@router.get("/assets/{asset_id}")
def public_catalog_image(asset_id: str) -> Response:
    if not CATALOG_ASSET_ID_PATTERN.fullmatch(asset_id):
        raise HTTPException(status_code=404, detail="Image not found.")
    try:
        image = get_catalog_image(asset_id)
    except (RuntimeError, GoogleAPIError, GoogleAuthError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Product image storage is not available.",
        ) from exc
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found.")
    image_data, content_type = image
    return Response(
        content=image_data,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=86400, immutable",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        },
    )


def _configured_sheet_settings() -> dict[str, Any]:
    try:
        configuration = get_google_sheets_settings()
    except (RuntimeError, GoogleAPIError, GoogleAuthError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Customer data storage is not configured or available.",
        ) from exc
    if not configuration["configured"]:
        raise HTTPException(
            status_code=503,
            detail="Customer data storage is not configured. Contact the site administrator.",
        )
    return configuration


def _append_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (GoogleAPIError, GoogleAuthError, RuntimeError)):
        return HTTPException(
            status_code=503,
            detail="Google Sheets is unavailable. The customer record was not saved.",
        )
    if isinstance(exc, httpx.HTTPStatusError):
        return HTTPException(
            status_code=502,
            detail="Google Sheets rejected the write. Verify sheet tabs and service-account Editor access.",
        )
    if isinstance(exc, (httpx.HTTPError, ValueError)):
        return HTTPException(
            status_code=502,
            detail="Google Sheets did not confirm the write. Please try again later.",
        )
    raise exc


def _timestamp() -> str:
    return datetime.now(LOCAL_TIMEZONE).isoformat(timespec="seconds")


def _record_number(prefix: str, now: datetime) -> str:
    return f"{prefix}{now:%Y%m%d}{secrets.randbelow(1_000_000):06d}"


@router.get("/content")
def public_site_content(response: Response) -> dict[str, Any]:
    try:
        content = get_site_content()
    except (RuntimeError, GoogleAPIError, GoogleAuthError) as exc:
        logger.error("Published site content unavailable: %s: %s", type(exc).__name__, exc)
        raise HTTPException(
            status_code=503,
            detail="Published website content is not available.",
        ) from exc
    response.headers["Cache-Control"] = "no-store"
    content["products"] = [
        product for product in content["products"] if product["active"]
    ]
    for product in content["products"]:
        product["image_url"] = (
            f"/api/v1/site/assets/{product['image_id']}"
            if product.get("image_id")
            else None
        )
    content["promotions"] = [
        promotion for promotion in content["promotions"] if promotion["active"]
    ]
    return content


@router.post("/orders", status_code=201)
async def submit_customer_order(order: CustomerOrderRequest) -> dict[str, str]:
    if not order.privacy_consent:
        raise HTTPException(
            status_code=422,
            detail="Consent to the Privacy Policy is required before submitting an order.",
        )
    try:
        content = get_site_content()
    except (RuntimeError, GoogleAPIError, GoogleAuthError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Product catalog is not available. The order was not saved.",
        ) from exc
    if not content["security"]["body"].strip():
        raise HTTPException(
            status_code=503,
            detail="The site administrator must publish a Privacy Policy before customer data can be saved.",
        )

    products = {
        product["product_id"]: product
        for product in content["products"]
        if product["active"]
    }
    quantities: dict[str, int] = {}
    for item in order.items:
        quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity

    order_lines = []
    total = 0.0
    for product_id, quantity in quantities.items():
        product = products.get(product_id)
        if product is None:
            raise HTTPException(
                status_code=409,
                detail=f"Product {product_id} is unavailable. Refresh the catalog and try again.",
            )
        if quantity > product["stock_quantity"]:
            raise HTTPException(
                status_code=409,
                detail=f"Requested quantity for {product['name']} exceeds available stock.",
            )
        unit_price = (
            product["sale_price"]
            if product["sale_price"] is not None
            else product["regular_price"]
        )
        total += unit_price * quantity
        order_lines.append(f"{product['name']} x {quantity}")

    now = datetime.now(LOCAL_TIMEZONE)
    order_number = _record_number("GD", now)
    consent_remark = f"Privacy Policy accepted at {now.isoformat(timespec='seconds')}"
    remark = " | ".join(part for part in (order.remark.strip(), consent_remark) if part)
    values = [
        now.strftime("%Y-%m-%d %H:%M:%S"),
        order_number,
        "เว็บไซต์",
        order.customer.strip(),
        order.address.strip(),
        order.address1.strip(),
        order.postcode,
        order.phone_number.strip(),
        "; ".join(order_lines),
        round(total, 2),
        remark,
        "เก็บเงินปลายทาง",
        round(total, 2),
        "",
        "รอยืนยันจากเจ้าหน้าที่",
    ]
    configuration = _configured_sheet_settings()
    try:
        await append_customer_row(
            spreadsheet_id=configuration["spreadsheet_id"],
            range_name=configuration["orders_range"],
            values=values,
        )
    except (GoogleAPIError, GoogleAuthError, RuntimeError, httpx.HTTPError, ValueError) as exc:
        raise _append_error(exc) from exc
    return {
        "status": "saved",
        "ordernumber": order_number,
        "message": "ได้รับคำขอแล้ว เจ้าหน้าที่จะตรวจสอบสินค้าและติดต่อกลับเพื่อยืนยันคำสั่งซื้อ",
    }


@router.post("/members", status_code=201)
async def register_member(member: MemberRegistrationRequest) -> dict[str, str]:
    if not member.privacy_consent:
        raise HTTPException(
            status_code=422,
            detail="Consent to the Privacy Policy is required before registration.",
        )
    try:
        content = get_site_content()
    except (RuntimeError, GoogleAPIError, GoogleAuthError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Published Privacy Policy is not available. Member data was not saved.",
        ) from exc
    if not content["security"]["body"].strip():
        raise HTTPException(
            status_code=503,
            detail="The site administrator must publish a Privacy Policy before customer data can be saved.",
        )
    configuration = _configured_sheet_settings()
    now = datetime.now(LOCAL_TIMEZONE)
    member_number = _record_number("MB", now)
    values = [
        now.strftime("%Y-%m-%d %H:%M:%S"),
        member_number,
        member.customer.strip(),
        member.phone_number.strip(),
        (member.email or "").strip(),
        f"ยินยอม Privacy Policy เมื่อ {now.isoformat(timespec='seconds')}",
    ]
    try:
        await append_customer_row(
            spreadsheet_id=configuration["spreadsheet_id"],
            range_name=configuration["member_range"],
            values=values,
        )
    except (GoogleAPIError, GoogleAuthError, RuntimeError, httpx.HTTPError, ValueError) as exc:
        raise _append_error(exc) from exc
    return {"status": "saved", "membernumber": member_number}
