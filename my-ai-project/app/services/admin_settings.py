from typing import Any

from app.config import settings


FIRESTORE_COLLECTION = "admin_settings"
GOOGLE_SHEETS_DOCUMENT = "google_sheets"


def _google_sheets_document() -> Any:
    if not settings.FIRESTORE_PROJECT_ID:
        raise RuntimeError("Firestore project is not configured.")

    from google.cloud import firestore

    client = firestore.Client(project=settings.FIRESTORE_PROJECT_ID)
    return client.collection(FIRESTORE_COLLECTION).document(GOOGLE_SHEETS_DOCUMENT)


def get_google_sheets_settings() -> dict[str, Any]:
    document = _google_sheets_document().get()
    if not document.exists:
        return {"configured": False, "spreadsheet_id": "", "range": ""}
    data = document.to_dict() or {}
    return {
        "configured": True,
        "spreadsheet_id": data.get("spreadsheet_id", ""),
        "range": data.get("range", ""),
    }


def save_google_sheets_settings(
    *,
    spreadsheet_id: str,
    range_name: str,
    updated_by: str,
) -> dict[str, Any]:
    from google.cloud import firestore

    document = _google_sheets_document()
    document.set(
        {
            "spreadsheet_id": spreadsheet_id,
            "range": range_name,
            "updated_by": updated_by,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
    )
    return {
        "configured": True,
        "spreadsheet_id": spreadsheet_id,
        "range": range_name,
    }
