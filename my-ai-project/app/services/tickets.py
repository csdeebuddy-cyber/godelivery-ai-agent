"""Conversation tickets for the Fasai voice/chat agent.

Ticket numbers look like FS-YYMMDD-NNNN (Thai local date, daily sequence).
Tickets live in Firestore `chat_tickets/{ticket_no}`; when Firestore is not
configured (local development) an in-memory store keeps the flow working.
"""

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.firebase.clients import get_firestore_client

logger = logging.getLogger(__name__)

TICKETS = "chat_tickets"
COUNTERS = "ticket_counters"
THAI_TZ = timezone(timedelta(hours=7))
MAX_TRANSCRIPT_LINES = 500

_memory_lock = threading.Lock()
_memory_tickets: dict[str, dict[str, Any]] = {}
_memory_counters: dict[str, int] = {}


def _now() -> datetime:
    return datetime.now(THAI_TZ)


def format_ticket_no(now: datetime, sequence: int) -> str:
    return f"FS-{now:%y%m%d}-{sequence:04d}"


def _firestore() -> Any | None:
    try:
        return get_firestore_client()
    except RuntimeError:
        return None


def _next_sequence_firestore(db: Any, day_key: str) -> int:
    from google.cloud import firestore

    counter_ref = db.collection(COUNTERS).document(day_key)

    @firestore.transactional
    def run(transaction: Any) -> int:
        snapshot = counter_ref.get(transaction=transaction)
        value = (snapshot.get("last") if snapshot.exists else 0) + 1
        transaction.set(counter_ref, {"last": value})
        return value

    return run(db.transaction())


def create_ticket(channel: str) -> dict[str, Any]:
    now = _now()
    day_key = f"{now:%y%m%d}"
    db = _firestore()
    if db is not None:
        sequence = _next_sequence_firestore(db, day_key)
    else:
        with _memory_lock:
            sequence = _memory_counters.get(day_key, 0) + 1
            _memory_counters[day_key] = sequence
    ticket_no = format_ticket_no(now, sequence)
    ticket = {
        "ticket_no": ticket_no,
        "channel": channel,
        "status": "open",
        "opened_at": now.isoformat(),
        "closed_at": None,
        "close_reason": None,
        "callback_requested": False,
        "callback_reason": None,
        "callback_details": None,
        "cart": [],
        "transcript": [],
    }
    if db is not None:
        db.collection(TICKETS).document(ticket_no).set(ticket)
    else:
        with _memory_lock:
            _memory_tickets[ticket_no] = ticket
    return ticket


def update_ticket(ticket_no: str, fields: dict[str, Any]) -> None:
    db = _firestore()
    if db is not None:
        db.collection(TICKETS).document(ticket_no).update(fields)
        return
    with _memory_lock:
        if ticket_no in _memory_tickets:
            _memory_tickets[ticket_no].update(fields)


def get_ticket(ticket_no: str) -> dict[str, Any] | None:
    db = _firestore()
    if db is not None:
        snapshot = db.collection(TICKETS).document(ticket_no).get()
        return snapshot.to_dict() if snapshot.exists else None
    with _memory_lock:
        ticket = _memory_tickets.get(ticket_no)
        return dict(ticket) if ticket else None


def request_callback(ticket_no: str, reason: str, details: str) -> None:
    update_ticket(
        ticket_no,
        {
            "callback_requested": True,
            "callback_reason": reason[:300],
            "callback_details": details[:1000],
            "callback_requested_at": _now().isoformat(),
        },
    )


def close_ticket(
    ticket_no: str,
    reason: str,
    transcript: list[dict[str, str]],
    cart: list[dict[str, Any]],
) -> None:
    update_ticket(
        ticket_no,
        {
            "status": "closed",
            "closed_at": _now().isoformat(),
            "close_reason": reason,
            "transcript": transcript[-MAX_TRANSCRIPT_LINES:],
            "cart": cart,
        },
    )
