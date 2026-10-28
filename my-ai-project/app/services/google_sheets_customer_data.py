from typing import Any
from urllib.parse import quote

import google.auth
import httpx
from google.auth.transport.requests import Request as GoogleAuthRequest
from starlette.concurrency import run_in_threadpool


SHEETS_WRITE_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
SHEETS_APPEND_URL = (
    "https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/"
    "{range_name}:append"
)


def _write_access_token() -> str:
    credentials, _ = google.auth.default(scopes=[SHEETS_WRITE_SCOPE])
    credentials.refresh(GoogleAuthRequest())
    if not credentials.token:
        raise RuntimeError("Google credentials did not provide an access token.")
    return credentials.token


async def append_customer_row(
    *,
    spreadsheet_id: str,
    range_name: str,
    values: list[Any],
) -> dict[str, Any]:
    access_token = await run_in_threadpool(_write_access_token)
    url = SHEETS_APPEND_URL.format(
        spreadsheet_id=quote(spreadsheet_id, safe=""),
        range_name=quote(range_name, safe=""),
    )
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            url,
            params={
                "valueInputOption": "RAW",
                "insertDataOption": "INSERT_ROWS",
            },
            headers={"Authorization": f"Bearer {access_token}"},
            json={"values": [values]},
        )
        response.raise_for_status()
    payload = response.json()
    updates = payload.get("updates") if isinstance(payload, dict) else None
    updated_range = updates.get("updatedRange") if isinstance(updates, dict) else None
    if not isinstance(updated_range, str):
        raise ValueError("Google Sheets did not confirm the appended row.")
    return {"updated_range": updated_range}
