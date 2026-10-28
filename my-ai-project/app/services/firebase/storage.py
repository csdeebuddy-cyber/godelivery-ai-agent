import logging
import re
from typing import Any
from uuid import uuid4

from google.api_core.exceptions import GoogleAPIError
from google.cloud import firestore

from app.services.firebase.clients import get_firestore_collection, get_storage_bucket
from app.services.firebase.security import safe_original_filename, validate_catalog_image


ASSET_COLLECTION = "site_assets"
CATALOG_IMAGE_PREFIX = "catalog"
logger = logging.getLogger(__name__)


def _asset_document(asset_id: str) -> Any:
    return get_firestore_collection(ASSET_COLLECTION).document(asset_id)


def upload_catalog_image(
    *,
    data: bytes,
    content_type: str,
    filename: str | None,
    uploaded_by: str,
    asset_id: str | None = None,
    source_url: str | None = None,
) -> dict[str, Any]:
    extension = validate_catalog_image(data, content_type)
    asset_id = asset_id or uuid4().hex
    object_path = f"{CATALOG_IMAGE_PREFIX}/{asset_id}{extension}"
    bucket = get_storage_bucket()
    blob = bucket.blob(object_path)
    blob.upload_from_string(
        data,
        content_type=content_type,
        if_generation_match=0,
    )
    metadata = {
        "asset_id": asset_id,
        "object_path": object_path,
        "filename": safe_original_filename(filename),
        "content_type": content_type,
        "size_bytes": len(data),
        "visibility": "public_catalog",
        "uploaded_by": uploaded_by,
        "uploaded_at": firestore.SERVER_TIMESTAMP,
    }
    if source_url:
        metadata["source_url"] = source_url
    try:
        _asset_document(asset_id).create(metadata)
    except GoogleAPIError:
        try:
            blob.delete()
        except GoogleAPIError:
            logger.exception("Could not remove orphaned Firebase Storage image %s.", asset_id)
        raise
    return {
        "asset_id": asset_id,
        "filename": metadata["filename"],
        "content_type": content_type,
        "size_bytes": len(data),
        "url": f"/api/v1/site/assets/{asset_id}",
    }


def list_catalog_images() -> list[dict[str, Any]]:
    documents = get_firestore_collection(ASSET_COLLECTION).stream()
    assets = []
    for document in documents:
        data = document.to_dict() or {}
        if data.get("visibility") != "public_catalog":
            continue
        assets.append(
            {
                "asset_id": document.id,
                "filename": data.get("filename", ""),
                "content_type": data.get("content_type", ""),
                "size_bytes": data.get("size_bytes", 0),
                "url": f"/api/v1/site/assets/{document.id}",
            }
        )
    return sorted(assets, key=lambda asset: asset["filename"].casefold())


def get_catalog_image(asset_id: str) -> tuple[bytes, str] | None:
    document = _asset_document(asset_id).get()
    if not document.exists:
        return None
    data = document.to_dict() or {}
    object_path = data.get("object_path")
    content_type = data.get("content_type")
    expected_path = (
        isinstance(object_path, str)
        and re.fullmatch(r"catalog/[a-f0-9]{32}\.(?:jpg|png|webp)", object_path)
        is not None
    )
    if (
        data.get("visibility") != "public_catalog"
        or not expected_path
        or not isinstance(content_type, str)
        or content_type not in {"image/jpeg", "image/png", "image/webp"}
    ):
        return None
    blob = get_storage_bucket().blob(object_path)
    return blob.download_as_bytes(), content_type
