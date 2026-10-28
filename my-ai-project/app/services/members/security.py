"""Crypto helpers: PIN hashing, device hashing, signed member sessions, bot heuristics."""

import base64
import hashlib
import hmac
import re
import secrets
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings


SESSION_COOKIE = "godelivery_member_session"
OAUTH_STATE_COOKIE = "godelivery_member_oauth_state"
SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
PENDING_MAX_AGE_SECONDS = 15 * 60
DEVICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{16,64}$")
BOT_USER_AGENT_PATTERN = re.compile(
    r"bot|crawler|spider|headless|phantomjs|selenium|puppeteer|playwright|"
    r"python-requests|python-httpx|curl/|wget/|scrapy",
    re.IGNORECASE,
)
_SCRYPT_PARAMS = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}


def session_secret() -> str | None:
    secret = settings.MEMBER_SESSION_SECRET or settings.ADMIN_SESSION_SECRET
    return secret if secret and len(secret) >= 32 else None


def oauth_config() -> dict[str, str] | None:
    client_id = settings.MEMBER_GOOGLE_CLIENT_ID or settings.ADMIN_GOOGLE_CLIENT_ID
    client_secret = settings.MEMBER_GOOGLE_CLIENT_SECRET or settings.ADMIN_GOOGLE_CLIENT_SECRET
    redirect_uri = settings.MEMBER_OAUTH_REDIRECT_URI
    secret = session_secret()
    if not (client_id and client_secret and redirect_uri and secret):
        return None
    return {"client_id": client_id, "client_secret": client_secret, "redirect_uri": redirect_uri}


def signer() -> URLSafeTimedSerializer:
    secret = session_secret()
    if secret is None:
        raise RuntimeError("Member session secret is not configured.")
    return URLSafeTimedSerializer(secret, salt="godelivery-member-session")


def read_signed(value: str | None, max_age: int) -> dict[str, Any] | None:
    if not value or session_secret() is None:
        return None
    try:
        data = signer().loads(value, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    return data if isinstance(data, dict) else None


def new_csrf_token() -> str:
    return secrets.token_urlsafe(24)


def hash_device_id(device_id: str) -> str:
    return hashlib.sha256(device_id.encode("utf-8")).hexdigest()


def hash_pin(pin: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(pin.encode("utf-8"), salt=salt, **_SCRYPT_PARAMS)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_pin(pin: str, stored: str) -> bool:
    try:
        scheme, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
    except ValueError:
        return False
    actual = hashlib.scrypt(pin.encode("utf-8"), salt=salt, **_SCRYPT_PARAMS)
    return hmac.compare_digest(actual, expected)


def looks_like_bot(user_agent: str | None) -> bool:
    return not user_agent or bool(BOT_USER_AGENT_PATTERN.search(user_agent))
