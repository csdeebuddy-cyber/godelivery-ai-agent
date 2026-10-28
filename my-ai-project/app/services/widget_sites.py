from typing import Any

from app.services.firebase.clients import get_firestore_collection


WIDGET_SITES_COLLECTION = "chat_widget_sites"


def _widget_sites_collection() -> Any:
    return get_firestore_collection(WIDGET_SITES_COLLECTION)


def list_widget_sites() -> list[dict[str, Any]]:
    documents = _widget_sites_collection().stream()
    sites = [
        {"site_id": document.id, **(document.to_dict() or {})}
        for document in documents
    ]
    return sorted(sites, key=lambda site: str(site.get("name", "")).casefold())


def get_widget_site(site_id: str) -> dict[str, Any] | None:
    document = _widget_sites_collection().document(site_id).get()
    if not document.exists:
        return None
    return {"site_id": document.id, **(document.to_dict() or {})}


def save_widget_site(
    *,
    site_id: str,
    configuration: dict[str, Any],
    created_by: str,
) -> dict[str, Any]:
    from google.cloud import firestore

    document = _widget_sites_collection().document(site_id)
    document.set(
        {
            **configuration,
            "created_by": created_by,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
    )
    return {"site_id": site_id, **configuration}


def delete_widget_site(site_id: str) -> None:
    _widget_sites_collection().document(site_id).delete()
