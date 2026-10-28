from typing import Any
from urllib.parse import quote

import google.auth
import httpx
from google.auth.transport.requests import Request as GoogleAuthRequest
from starlette.concurrency import run_in_threadpool


SHEETS_READONLY_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"
SHEETS_VALUES_URL = "https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{range_name}"


def _access_token() -> str:
    credentials, _ = google.auth.default(scopes=[SHEETS_READONLY_SCOPE])
    credentials.refresh(GoogleAuthRequest())
    if not credentials.token:
        raise RuntimeError("Google credentials did not provide an access token.")
    return credentials.token


async def _read_values(
    client: httpx.AsyncClient,
    *,
    access_token: str,
    spreadsheet_id: str,
    range_name: str,
) -> list[list[Any]]:
    url = SHEETS_VALUES_URL.format(
        spreadsheet_id=quote(spreadsheet_id, safe=""),
        range_name=quote(range_name, safe=""),
    )
    response = await client.get(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    response.raise_for_status()
    payload = response.json()
    values = payload.get("values", []) if isinstance(payload, dict) else []
    if not isinstance(values, list) or any(not isinstance(row, list) for row in values):
        raise ValueError(f"Google Sheets returned invalid rows for range {range_name}.")
    return values


def _cell(row: list[Any], column: int) -> str:
    if column > len(row) or row[column - 1] is None:
        return ""
    return str(row[column - 1]).strip()


def _optional_number(
    value: str,
    *,
    row_number: int,
    field_label: str,
    integer: bool = False,
    allow_zero: bool = False,
) -> int | float | None:
    if not value:
        return None
    try:
        number = float(value)
    except ValueError as exc:
        raise ValueError(
            f"Google Sheet row {row_number} has an invalid {field_label}."
        ) from exc
    if (
        number < 0
        or (number == 0 and not allow_zero)
        or (integer and not number.is_integer())
    ):
        raise ValueError(f"Google Sheet row {row_number} has an invalid {field_label}.")
    return int(number) if integer else number


def _map_products(
    rows: list[list[Any]],
    columns: dict[str, int],
) -> list[dict[str, Any]]:
    products = []
    for row_number, row in enumerate(rows, start=2):
        product_id = _cell(row, columns["product_id"])
        name = _cell(row, columns["product_name"])
        if not product_id or not name:
            raise ValueError(
                f"Google Sheet row {row_number} must include product ID and name."
            )
        products.append(
            {
                "id": product_id,
                "name": name,
                "price_regular": _optional_number(
                    _cell(row, columns["regular_price"]),
                    row_number=row_number,
                    field_label="regular price",
                ),
                "price_sale": _optional_number(
                    _cell(row, columns["selling_price"]),
                    row_number=row_number,
                    field_label="selling price",
                ),
                "stock_quantity": _optional_number(
                    _cell(row, columns["stock_quantity"]),
                    row_number=row_number,
                    field_label="stock quantity",
                    integer=True,
                    allow_zero=True,
                ),
            }
        )
    return products


def _map_promotions(
    rows: list[list[Any]],
    columns: dict[str, int],
) -> list[dict[str, str]]:
    promotions = []
    for row_number, row in enumerate(rows, start=2):
        promotion_id = _cell(row, columns["promotion_id"])
        title = _cell(row, columns["promotion_name"])
        if not promotion_id or not title:
            raise ValueError(
                f"Google Sheet row {row_number} must include promotion ID and name."
            )
        promotions.append(
            {
                "promo_id": promotion_id,
                "title": title,
                "details": _cell(row, columns["conditions"]),
            }
        )
    return promotions


async def preview_google_sheets_knowledge(
    configuration: dict[str, Any],
) -> dict[str, Any]:
    spreadsheet_id = str(configuration["spreadsheet_id"])
    access_token = await run_in_threadpool(_access_token)
    async with httpx.AsyncClient(timeout=15) as client:
        product_rows = await _read_values(
            client,
            access_token=access_token,
            spreadsheet_id=spreadsheet_id,
            range_name=configuration["range"],
        )
        promotion_rows = await _read_values(
            client,
            access_token=access_token,
            spreadsheet_id=spreadsheet_id,
            range_name=configuration["promotion_range"],
        )

    return {
        "spreadsheet_id": spreadsheet_id,
        "products_range": configuration["range"],
        "promotions_range": configuration["promotion_range"],
        "products": _map_products(product_rows, configuration["product_columns"]),
        "promotions": _map_promotions(
            promotion_rows, configuration["promotion_columns"]
        ),
        "private_tabs": {
            "orders_range": configuration["orders_range"],
            "member_range": configuration["member_range"],
            "read": False,
        },
        "persisted": False,
    }
