"""Member sign-up / PIN / device / bot-lock flow."""

from datetime import datetime, timezone
from typing import Any

from app.services.members import repository as repo
from app.services.members import security


class MemberError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def _locked() -> MemberError:
    return MemberError(423, "account_locked", "บัญชีนี้ถูกล็อคเพื่อความปลอดภัย กรุณาติดต่อเจ้าหน้าที่")


def lock_for_bot(
    *,
    device_hash: str,
    customer_no: str | None,
    signal: str,
    user_agent: str,
    ip: str,
) -> None:
    """Record the evidence, block the device and lock the member immediately."""
    newly_blocked = repo.block_device(device_hash, f"bot:{signal}", customer_no)
    if customer_no:
        repo.lock_member(customer_no, f"bot:{signal}")
    if newly_blocked or customer_no:
        repo.log_security_event(
            "bot_detected",
            signal=signal,
            customer_no=customer_no,
            device_hash=device_hash,
            user_agent=user_agent[:300],
            ip=ip,
        )


def sign_in_with_google(
    *, email: str, name: str, device_id: str, user_agent: str, ip: str
) -> tuple[dict[str, Any], str, str, bool]:
    """Returns (member, device_hash, stage, created) where stage is setup_pin, verify_pin or active."""
    device_hash = security.hash_device_id(device_id)
    member, created = repo.get_or_create_member(email, name)
    customer_no = member["customer_no"]
    if created:
        repo.log_security_event("member_registered", customer_no=customer_no, device_hash=device_hash)

    if security.looks_like_bot(user_agent):
        lock_for_bot(
            device_hash=device_hash,
            customer_no=customer_no,
            signal="user_agent",
            user_agent=user_agent,
            ip=ip,
        )
        raise _locked()

    device = repo.record_device(customer_no, device_hash, user_agent, ip)
    repo.log_security_event("sign_in", customer_no=customer_no, device_hash=device_hash, ip=ip)

    if member.get("status") == "locked" or repo.is_device_blocked(device_hash):
        raise _locked()
    if not member.get("pin_hash"):
        return member, device_hash, "setup_pin", created
    if device.get("trusted"):
        return member, device_hash, "active", created
    return member, device_hash, "verify_pin", created


def load_member(customer_no: str, device_hash: str) -> dict[str, Any]:
    member = repo.get_member(customer_no)
    if member is None:
        raise MemberError(401, "unauthenticated", "กรุณาเข้าสู่ระบบ")
    if member.get("status") == "locked" or repo.is_device_blocked(device_hash):
        raise _locked()
    return member


def set_pin(customer_no: str, device_hash: str, pin: str, confirm_pin: str) -> dict[str, Any]:
    member = load_member(customer_no, device_hash)
    if member.get("pin_hash"):
        raise MemberError(409, "pin_exists", "บัญชีนี้มี PIN อยู่แล้ว ไม่สามารถสร้างใหม่ได้")
    if pin != confirm_pin:
        raise MemberError(422, "pin_mismatch", "PIN ที่ยืนยันไม่ตรงกัน")
    member = repo.update_member(customer_no, {"pin_hash": security.hash_pin(pin)})
    repo.trust_device(customer_no, device_hash)
    repo.log_security_event("pin_created", customer_no=customer_no, device_hash=device_hash)
    return member


def check_pin(customer_no: str, device_hash: str, pin: str) -> dict[str, Any]:
    member = load_member(customer_no, device_hash)
    stored = member.get("pin_hash")
    if not stored:
        raise MemberError(409, "pin_missing", "ยังไม่ได้สร้าง PIN")
    locked_until = member.get("pin_locked_until")
    if isinstance(locked_until, datetime) and locked_until > datetime.now(timezone.utc):
        raise MemberError(429, "pin_cooldown", "กรอก PIN ผิดหลายครั้ง กรุณารอ 15 นาทีแล้วลองใหม่")
    if not security.verify_pin(pin, stored):
        repo.register_pin_failure(customer_no)
        repo.log_security_event("pin_failed", customer_no=customer_no, device_hash=device_hash)
        raise MemberError(401, "pin_invalid", "PIN ไม่ถูกต้อง")
    repo.reset_pin_failures(customer_no)
    repo.trust_device(customer_no, device_hash)
    repo.log_security_event("device_trusted", customer_no=customer_no, device_hash=device_hash)
    return member


def update_profile(customer_no: str, device_hash: str, fields: dict[str, str]) -> dict[str, Any]:
    load_member(customer_no, device_hash)
    allowed = {"name", "address", "address1", "postcode", "phone"}
    clean = {key: value.strip() for key, value in fields.items() if key in allowed}
    return repo.update_member(customer_no, clean)


def public_profile(member: dict[str, Any]) -> dict[str, Any]:
    return {
        "customer_no": member.get("customer_no"),
        "email": member.get("email"),
        "name": member.get("name", ""),
        "address": member.get("address", ""),
        "address1": member.get("address1", ""),
        "postcode": member.get("postcode", ""),
        "phone": member.get("phone", ""),
    }


def load_member_unchecked(customer_no: str) -> dict[str, Any] | None:
    return repo.get_member(customer_no)
