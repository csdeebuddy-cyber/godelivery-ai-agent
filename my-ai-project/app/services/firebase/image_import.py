import hashlib
from typing import Any
from urllib.parse import urlsplit

import httpx
from starlette.concurrency import run_in_threadpool

from app.services.firebase.security import ALLOWED_IMAGE_TYPES, MAX_IMAGE_SIZE_BYTES
from app.services.firebase.storage import _asset_document, upload_catalog_image


ALLOWED_HOSTS = {"firebasestorage.googleapis.com", "storage.googleapis.com"}
ALLOWED_HOST_SUFFIXES = (".firebasestorage.app", ".appspot.com")
MAX_URL_LENGTH = 2000


class ImageLinkError(ValueError):
    pass


def validate_source_url(url: str) -> str:
    url = url.strip()
    if not url or len(url) > MAX_URL_LENGTH:
        raise ImageLinkError("ลิงก์ภาพไม่ถูกต้อง")
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or parts.username or parts.password or parts.port not in (None, 443):
        raise ImageLinkError("ลิงก์ต้องเป็น https ของ Firebase Storage เท่านั้น")
    if host not in ALLOWED_HOSTS and not host.endswith(ALLOWED_HOST_SUFFIXES):
        raise ImageLinkError("รองรับเฉพาะลิงก์จาก Firebase Storage")
    return url


def _detect_content_type(data: bytes) -> str:
    for content_type, (_, signature_check) in ALLOWED_IMAGE_TYPES.items():
        if signature_check(data):
            return content_type
    raise ImageLinkError("ลิงก์นี้ไม่ใช่ภาพ JPEG, PNG หรือ WebP")


async def _download(url: str) -> bytes:
    data = bytearray()
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            async with client.stream("GET", url) as response:
                if response.status_code != 200:
                    raise ImageLinkError(f"ดึงภาพไม่สำเร็จ (HTTP {response.status_code})")
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_IMAGE_SIZE_BYTES:
                        raise ImageLinkError("รูปภาพต้องมีขนาดไม่เกิน 5 MB")
    except httpx.HTTPError as exc:
        raise ImageLinkError("เชื่อมต่อลิงก์ภาพไม่ได้") from exc
    return bytes(data)


def _asset_id_for(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


def _existing_asset(asset_id: str) -> dict[str, Any] | None:
    document = _asset_document(asset_id).get()
    if not document.exists:
        return None
    data = document.to_dict() or {}
    return {
        "asset_id": asset_id,
        "filename": data.get("filename", ""),
        "content_type": data.get("content_type", ""),
        "size_bytes": data.get("size_bytes", 0),
        "url": f"/api/v1/site/assets/{asset_id}",
    }


async def import_catalog_image(url: str, uploaded_by: str) -> dict[str, Any]:
    """Copy an image from a Firebase link into the catalog; the same link is stored once."""
    url = validate_source_url(url)
    asset_id = _asset_id_for(url)
    existing = await run_in_threadpool(_existing_asset, asset_id)
    if existing is not None:
        return {**existing, "reused": True}
    data = await _download(url)
    content_type = _detect_content_type(data)
    filename = urlsplit(url).path.rsplit("/", 1)[-1] or "image"
    saved = await run_in_threadpool(
        lambda: upload_catalog_image(
            data=data,
            content_type=content_type,
            filename=filename,
            uploaded_by=uploaded_by,
            asset_id=asset_id,
            source_url=url,
        )
    )
    return {**saved, "reused": False}
