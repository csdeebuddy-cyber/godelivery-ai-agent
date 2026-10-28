from typing import Any

from app.services.firebase.clients import get_firestore_document
from app.schemas.site_content import SiteContent


FIRESTORE_COLLECTION = "admin_settings"
SITE_CONTENT_DOCUMENT = "homepage_content"


def _site_content_document() -> Any:
    return get_firestore_document(FIRESTORE_COLLECTION, SITE_CONTENT_DOCUMENT)


def get_site_content() -> dict[str, Any]:
    document = _site_content_document().get()
    if not document.exists:
        return SiteContent().model_dump()
    data = document.to_dict() or {}
    data.pop("updated_by", None)
    data.pop("updated_at", None)
    return SiteContent.model_validate(data).model_dump()


def save_site_content(content: SiteContent, *, updated_by: str) -> dict[str, Any]:
    from google.cloud import firestore

    data = content.model_dump(mode="json")
    _site_content_document().set(
        {
            **data,
            "updated_by": updated_by,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
    )
    return data
