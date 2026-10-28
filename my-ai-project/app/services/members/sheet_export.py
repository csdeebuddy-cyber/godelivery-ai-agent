"""Export member records to the Google Sheet configured in the admin settings."""

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from starlette.concurrency import run_in_threadpool

from app.services.admin_settings import get_google_sheets_settings
from app.services.google_sheets_customer_data import append_customer_row


logger = logging.getLogger(__name__)
LOCAL_TIMEZONE = ZoneInfo("Asia/Bangkok")

# Column order: timestamp, customer no., name, address, address 1, postcode,
# email, phone, status, event.
def member_row(member: dict[str, Any], event: str) -> list[Any]:
    return [
        datetime.now(LOCAL_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S"),
        member.get("customer_no", ""),
        member.get("name", ""),
        member.get("address", ""),
        member.get("address1", ""),
        member.get("postcode", ""),
        member.get("email", ""),
        member.get("phone", ""),
        member.get("status", ""),
        event,
    ]


async def export_member(member: dict[str, Any], event: str) -> bool:
    """Best effort: the Firestore write is the source of truth, so failures are only logged."""
    try:
        configuration = await run_in_threadpool(get_google_sheets_settings)
        if not configuration["configured"]:
            logger.warning("Google Sheets is not configured; member export skipped.")
            return False
        await append_customer_row(
            spreadsheet_id=configuration["spreadsheet_id"],
            range_name=configuration["member_range"],
            values=member_row(member, event),
        )
        return True
    except Exception:
        logger.exception("Member export to Google Sheets failed for %s.", member.get("customer_no"))
        return False
