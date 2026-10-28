"""Firestore persistence for members.

Layout (Firestore is the database; Google Sheets is an export target):
  members/{customer_no}                  profile, PIN hash, status
  members/{customer_no}/devices/{hash}   every device that signed in
  member_emails/{sha256(email)}          unique email -> customer_no index
  member_counters/members                sequential customer-number counter
  member_blocked_devices/{hash}          devices locked after bot detection
  member_security_events/{auto}          audit trail
"""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from google.cloud import firestore

from app.services.firebase.clients import get_firestore_client


MEMBERS = "members"
EMAIL_INDEX = "member_emails"
COUNTERS = "member_counters"
BLOCKED_DEVICES = "member_blocked_devices"
SECURITY_EVENTS = "member_security_events"
MAX_PIN_FAILURES = 5
PIN_COOLDOWN = timedelta(minutes=15)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _db() -> Any:
    return get_firestore_client()


def _public(snapshot: Any) -> dict[str, Any] | None:
    if not snapshot.exists:
        return None
    return snapshot.to_dict() or {}


def get_member(customer_no: str) -> dict[str, Any] | None:
    return _public(_db().collection(MEMBERS).document(customer_no).get())


def get_or_create_member(email: str, name_hint: str = "") -> tuple[dict[str, Any], bool]:
    """Create on first sign-up (auto customer number), otherwise return the existing member."""
    db = _db()
    email_key = hashlib.sha256(email.casefold().encode("utf-8")).hexdigest()
    index_ref = db.collection(EMAIL_INDEX).document(email_key)
    counter_ref = db.collection(COUNTERS).document("members")

    @firestore.transactional
    def run(transaction: Any) -> tuple[dict[str, Any], bool]:
        index = index_ref.get(transaction=transaction)
        if index.exists:
            member_ref = db.collection(MEMBERS).document(index.get("customer_no"))
            return (member_ref.get(transaction=transaction).to_dict() or {}), False
        counter = counter_ref.get(transaction=transaction)
        next_number = (counter.get("last") if counter.exists else 0) + 1
        # 5-digit customer numbers, 10001-99999 (no leading zeros in /user/xxxxx URLs).
        if next_number > 89_999:
            raise RuntimeError("Customer number range is exhausted.")
        customer_no = str(10_000 + next_number)
        now = _now()
        member = {
            "customer_no": customer_no,
            "email": email.casefold(),
            "name": "",
            "address": "",
            "address1": "",
            "postcode": "",
            "phone": "",
            "google_name": name_hint,
            "pin_hash": None,
            "failed_pin_attempts": 0,
            "pin_locked_until": None,
            "status": "active",
            "lock_reason": None,
            "created_at": now,
            "updated_at": now,
        }
        transaction.set(counter_ref, {"last": next_number})
        transaction.set(index_ref, {"customer_no": customer_no})
        transaction.set(db.collection(MEMBERS).document(customer_no), member)
        return member, True

    return run(db.transaction())


def update_member(customer_no: str, fields: dict[str, Any]) -> dict[str, Any]:
    ref = _db().collection(MEMBERS).document(customer_no)
    ref.update({**fields, "updated_at": _now()})
    return ref.get().to_dict() or {}


def record_device(
    customer_no: str, device_hash: str, user_agent: str, ip: str
) -> dict[str, Any]:
    """Upsert the device on every sign-in. Returns the stored record (before this visit)."""
    ref = _db().collection(MEMBERS).document(customer_no).collection("devices").document(device_hash)
    snapshot = ref.get()
    now = _now()
    if snapshot.exists:
        previous = snapshot.to_dict() or {}
        ref.update(
            {
                "last_seen_at": now,
                "login_count": firestore.Increment(1),
                "user_agent": user_agent[:300],
                "ip": ip,
            }
        )
        return previous
    record = {
        "device_hash": device_hash,
        "first_seen_at": now,
        "last_seen_at": now,
        "login_count": 1,
        "trusted": False,
        "user_agent": user_agent[:300],
        "ip": ip,
    }
    ref.set(record)
    return record


def trust_device(customer_no: str, device_hash: str) -> None:
    ref = _db().collection(MEMBERS).document(customer_no).collection("devices").document(device_hash)
    ref.set({"trusted": True, "trusted_at": _now()}, merge=True)


def list_devices(customer_no: str) -> list[dict[str, Any]]:
    docs = _db().collection(MEMBERS).document(customer_no).collection("devices").stream()
    return [doc.to_dict() or {} for doc in docs]


def register_pin_failure(customer_no: str) -> dict[str, Any]:
    ref = _db().collection(MEMBERS).document(customer_no)
    member = ref.get().to_dict() or {}
    failures = int(member.get("failed_pin_attempts", 0)) + 1
    fields: dict[str, Any] = {"failed_pin_attempts": failures, "updated_at": _now()}
    if failures >= MAX_PIN_FAILURES:
        fields["failed_pin_attempts"] = 0
        fields["pin_locked_until"] = _now() + PIN_COOLDOWN
    ref.update(fields)
    return fields


def reset_pin_failures(customer_no: str) -> None:
    _db().collection(MEMBERS).document(customer_no).update(
        {"failed_pin_attempts": 0, "pin_locked_until": None}
    )


def is_device_blocked(device_hash: str) -> bool:
    return _db().collection(BLOCKED_DEVICES).document(device_hash).get().exists


def block_device(device_hash: str, reason: str, customer_no: str | None) -> bool:
    """Returns True when the device was newly blocked."""
    ref = _db().collection(BLOCKED_DEVICES).document(device_hash)
    if ref.get().exists:
        return False
    ref.set({"reason": reason, "customer_no": customer_no, "blocked_at": _now()})
    return True


def lock_member(customer_no: str, reason: str) -> None:
    update_member(customer_no, {"status": "locked", "lock_reason": reason})


def log_security_event(event_type: str, **details: Any) -> None:
    _db().collection(SECURITY_EVENTS).add({"type": event_type, "at": _now(), **details})
