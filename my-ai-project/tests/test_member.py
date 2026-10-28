import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services.members import repository as repo
from app.services.members import security, service


class FakeStore:
    """In-memory stand-in for the Firestore-backed repository."""

    def __init__(self) -> None:
        self.members: dict[str, dict] = {}
        self.devices: dict[tuple[str, str], dict] = {}
        self.blocked: set[str] = set()
        self.events: list[str] = []

    def get_or_create_member(self, email, name_hint=""):
        for member in self.members.values():
            if member["email"] == email.casefold():
                return dict(member), False
        number = str(10_000 + len(self.members) + 1)
        member = {
            "customer_no": number, "email": email.casefold(), "name": "", "address": "",
            "address1": "", "postcode": "", "phone": "", "pin_hash": None,
            "status": "active", "pin_locked_until": None, "failed_pin_attempts": 0,
        }
        self.members[number] = member
        return dict(member), True

    def get_member(self, no):
        member = self.members.get(no)
        return dict(member) if member else None

    def update_member(self, no, fields):
        self.members[no].update(fields)
        return dict(self.members[no])

    def record_device(self, no, device_hash, ua, ip):
        previous = self.devices.get((no, device_hash))
        if previous is None:
            self.devices[(no, device_hash)] = {"trusted": False}
            return {"trusted": False}
        return dict(previous)

    def trust_device(self, no, device_hash):
        self.devices.setdefault((no, device_hash), {})["trusted"] = True

    def register_pin_failure(self, no):
        return {}

    def reset_pin_failures(self, no):
        pass

    def is_device_blocked(self, device_hash):
        return device_hash in self.blocked

    def block_device(self, device_hash, reason, no):
        new = device_hash not in self.blocked
        self.blocked.add(device_hash)
        return new

    def lock_member(self, no, reason):
        self.members[no].update(status="locked", lock_reason=reason)

    def log_security_event(self, event_type, **details):
        self.events.append(event_type)


BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
DEVICE_A = "a" * 32
DEVICE_B = "b" * 32


class MemberFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = FakeStore()
        self.patches = [
            patch.object(settings, "ADMIN_SESSION_SECRET", "x" * 40),
            patch.object(settings, "MEMBER_SESSION_SECRET", None),
            patch("app.api.v1.endpoints.member.export_member", new=AsyncMock(return_value=True)),
        ]
        for name in dir(FakeStore):
            if hasattr(repo, name) and not name.startswith("_"):
                self.patches.append(patch.object(repo, name, getattr(self.store, name)))
        for item in self.patches:
            item.start()
        self.client = TestClient(app, headers={"user-agent": BROWSER_UA})

    def tearDown(self) -> None:
        for item in self.patches:
            item.stop()

    def sign_in(self, device_id: str, email: str = "user@example.com") -> str:
        member, device_hash, stage, _ = service.sign_in_with_google(
            email=email, name="U", device_id=device_id, user_agent=BROWSER_UA, ip="1.1.1.1"
        )
        from app.api.v1.endpoints.member import _issue_session
        from fastapi import Response

        response = Response()
        _issue_session(response, member["customer_no"], device_hash, stage)
        self.client.cookies.clear()
        self.client.cookies.set(
            security.SESSION_COOKIE,
            response.headers["set-cookie"].split(";")[0].split("=", 1)[1],
        )
        return stage

    def csrf(self) -> dict[str, str]:
        return {"X-CSRF-Token": self.client.get("/api/v1/member/me").json()["csrf_token"]}

    def test_first_signup_requires_pin_then_new_device_requires_same_pin(self) -> None:
        self.assertEqual(self.sign_in(DEVICE_A), "setup_pin")
        self.assertEqual(list(self.store.members), ["10001"])
        bad = self.client.post(
            "/api/v1/member/pin/setup", json={"pin": "123456", "confirm_pin": "654321"},
            headers=self.csrf(),
        )
        self.assertEqual(bad.status_code, 422)
        ok = self.client.post(
            "/api/v1/member/pin/setup", json={"pin": "123456", "confirm_pin": "123456"},
            headers=self.csrf(),
        )
        self.assertEqual(ok.status_code, 200)

        self.assertEqual(self.sign_in(DEVICE_A), "active")
        self.assertEqual(self.client.get("/user/10001", follow_redirects=False).status_code, 200)
        self.assertEqual(self.client.get("/user/10002", follow_redirects=False).status_code, 303)
        self.assertEqual(self.sign_in(DEVICE_B), "verify_pin")
        wrong = self.client.post(
            "/api/v1/member/pin/verify", json={"pin": "000000"}, headers=self.csrf()
        )
        self.assertEqual(wrong.status_code, 401)
        right = self.client.post(
            "/api/v1/member/pin/verify", json={"pin": "123456"}, headers=self.csrf()
        )
        self.assertEqual(right.status_code, 200)
        self.assertEqual(len([k for k in self.store.devices if k[1]]), 2)
        self.assertEqual(self.sign_in(DEVICE_B), "active")

    def test_profile_update_requires_csrf_and_active_stage(self) -> None:
        self.sign_in(DEVICE_A)
        response = self.client.put("/api/v1/member/profile", json={"name": "A"})
        self.assertEqual(response.status_code, 403)

    def test_honeypot_locks_member_and_device(self) -> None:
        self.sign_in(DEVICE_A)
        response = self.client.post(
            "/api/v1/member/pin/setup",
            json={"pin": "123456", "confirm_pin": "123456", "website": "http://spam"},
            headers=self.csrf(),
        )
        self.assertEqual(response.status_code, 423)
        self.assertEqual(self.store.members["10001"]["status"], "locked")
        self.assertIn(security.hash_device_id(DEVICE_A), self.store.blocked)
        self.assertIn("bot_detected", self.store.events)
        with self.assertRaises(service.MemberError):
            self.sign_in(DEVICE_B)

    def test_bot_user_agent_is_locked_at_sign_in(self) -> None:
        with self.assertRaises(service.MemberError) as raised:
            service.sign_in_with_google(
                email="bot@example.com", name="", device_id=DEVICE_A,
                user_agent="python-requests/2.31", ip="2.2.2.2",
            )
        self.assertEqual(raised.exception.status_code, 423)
        self.assertEqual(self.store.members["10001"]["status"], "locked")

    def test_pin_hash_roundtrip(self) -> None:
        stored = security.hash_pin("123456")
        self.assertTrue(security.verify_pin("123456", stored))
        self.assertFalse(security.verify_pin("123457", stored))


if __name__ == "__main__":
    unittest.main()
