from typing import Any

from app.config import settings


FIRESTORE_COLLECTION = "admin_settings"
GOOGLE_SHEETS_DOCUMENT = "google_sheets"
DEFAULT_PRODUCT_COLUMNS = {
    "product_id": 1,
    "product_name": 2,
    "regular_price": 3,
    "selling_price": 4,
    "stock_quantity": 5,
}
DEFAULT_PROMOTION_COLUMNS = {
    "promotion_id": 1,
    "promotion_name": 2,
    "conditions": 3,
}


def _google_sheets_document() -> Any:
    if not settings.FIRESTORE_PROJECT_ID:
        raise RuntimeError("Firestore project is not configured.")

    from google.cloud import firestore

    client = firestore.Client(project=settings.FIRESTORE_PROJECT_ID)
    return client.collection(FIRESTORE_COLLECTION).document(GOOGLE_SHEETS_DOCUMENT)


def get_google_sheets_settings() -> dict[str, Any]:
    document = _google_sheets_document().get()
    if not document.exists:
        return {
            "configured": False,
            "spreadsheet_id": "",
            "range": "product!A2:E",
            "product_columns": DEFAULT_PRODUCT_COLUMNS.copy(),
            "promotion_range": "promotion!A2:C",
            "promotion_columns": DEFAULT_PROMOTION_COLUMNS.copy(),
            "orders_range": "orders!A2:Z",
            "member_range": "MEMBER!A2:Z",
        }
    data = document.to_dict() or {}
    return {
        "configured": True,
        "spreadsheet_id": data.get("spreadsheet_id", ""),
        "range": data.get("range", "product!A2:E"),
        "product_columns": {
            **DEFAULT_PRODUCT_COLUMNS,
            **(data.get("product_columns") or {}),
        },
        "promotion_range": data.get("promotion_range", "promotion!A2:C"),
        "promotion_columns": {
            **DEFAULT_PROMOTION_COLUMNS,
            **(data.get("promotion_columns") or {}),
        },
        "orders_range": data.get("orders_range", "orders!A2:Z"),
        "member_range": data.get("member_range", "MEMBER!A2:Z"),
    }


def save_google_sheets_settings(
    *,
    spreadsheet_id: str,
    range_name: str,
    product_columns: dict[str, int],
    promotion_range: str,
    promotion_columns: dict[str, int],
    orders_range: str,
    member_range: str,
    updated_by: str,
) -> dict[str, Any]:
    from google.cloud import firestore

    document = _google_sheets_document()
    document.set(
        {
            "spreadsheet_id": spreadsheet_id,
            "range": range_name,
            "product_columns": product_columns,
            "promotion_range": promotion_range,
            "promotion_columns": promotion_columns,
            "orders_range": orders_range,
            "member_range": member_range,
            "updated_by": updated_by,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
    )
    return {
        "configured": True,
        "spreadsheet_id": spreadsheet_id,
        "range": range_name,
        "product_columns": product_columns,
        "promotion_range": promotion_range,
        "promotion_columns": promotion_columns,
        "orders_range": orders_range,
        "member_range": member_range,
    }
