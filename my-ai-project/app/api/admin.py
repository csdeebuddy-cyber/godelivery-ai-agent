import base64
import hashlib
import secrets
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from google.auth import exceptions as google_auth_exceptions
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings
from app.services.knowledge_base import get_knowledge_base_status


router = APIRouter(tags=["admin"])
api_router = APIRouter(prefix="/admin", tags=["admin"])
STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
ALLOWED_ADMIN_EMAIL = "smpmfast@gmail.com"
ADMIN_SESSION_COOKIE = "godelivery_admin_session"
OAUTH_STATE_COOKIE = "godelivery_admin_oauth_state"
SESSION_MAX_AGE_SECONDS = 12 * 60 * 60
GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def _session_signer() -> URLSafeTimedSerializer:
    secret = settings.ADMIN_SESSION_SECRET
    if not secret or len(secret) < 32:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "admin_session_not_configured",
                "message": "Admin session signing secret is not configured.",
            },
        )
    return URLSafeTimedSerializer(secret, salt="godelivery-admin-session")


def _oauth_ready() -> bool:
    return all(
        (
            settings.ADMIN_GOOGLE_CLIENT_ID,
            settings.ADMIN_GOOGLE_CLIENT_SECRET,
            settings.ADMIN_OAUTH_REDIRECT_URI,
            settings.ADMIN_SESSION_SECRET and len(settings.ADMIN_SESSION_SECRET) >= 32,
        )
    )


def _secure_cookie() -> bool:
    return settings.APP_ENV.casefold() in {"production", "prod"}


def _admin_email_from_cookie(request: Request) -> str | None:
    signed_session = request.cookies.get(ADMIN_SESSION_COOKIE)
    if not signed_session or not settings.ADMIN_SESSION_SECRET:
        return None
    try:
        session: Any = _session_signer().loads(
            signed_session,
            max_age=SESSION_MAX_AGE_SECONDS,
        )
    except (BadSignature, SignatureExpired, HTTPException):
        return None
    email = session.get("email") if isinstance(session, dict) else None
    if not isinstance(email, str) or email.casefold() != ALLOWED_ADMIN_EMAIL:
        return None
    return email


def _require_admin(request: Request) -> str:
    email = _admin_email_from_cookie(request)
    if email is None:
        raise HTTPException(status_code=401, detail="Admin authentication required.")
    return email


def _set_auth_cookies(response: Response, signed_session: str) -> None:
    response.set_cookie(
        ADMIN_SESSION_COOKIE,
        signed_session,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=_secure_cookie(),
        samesite="lax",
        path="/",
    )
    response.delete_cookie(
        OAUTH_STATE_COOKIE,
        httponly=True,
        secure=_secure_cookie(),
        samesite="lax",
        path="/",
    )


@router.get("/dashboard/admin", include_in_schema=False)
async def admin_dashboard(request: Request) -> Response:
    if _admin_email_from_cookie(request) is None:
        return RedirectResponse("/dashboard/admin/login", status_code=303)
    return FileResponse(STATIC_DIR / "admin.html")


@router.get("/dashboard/admin/login", include_in_schema=False)
async def admin_login_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "admin-login.html")


@router.get("/admin/auth/google/login", include_in_schema=False)
async def google_login() -> Response:
    if not _oauth_ready():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "google_sso_not_configured",
                "message": (
                    "Google OAuth Client ID, Client Secret, redirect URI, and a "
                    "32-character session secret must be configured before sign-in."
                ),
            },
        )

    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    signer = _session_signer()
    query = urlencode(
        {
            "client_id": settings.ADMIN_GOOGLE_CLIENT_ID,
            "redirect_uri": settings.ADMIN_OAUTH_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
    )
    response = RedirectResponse(f"{GOOGLE_AUTHORIZE_URL}?{query}", status_code=302)
    response.set_cookie(
        OAUTH_STATE_COOKIE,
        signer.dumps({"state": state, "code_verifier": code_verifier}),
        max_age=600,
        httponly=True,
        secure=_secure_cookie(),
        samesite="lax",
        path="/",
    )
    return response


@router.get("/admin/auth/google/callback", name="google_oauth_callback", include_in_schema=False)
async def google_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Response:
    if error or not code or not state or not _oauth_ready():
        return RedirectResponse("/dashboard/admin/login?error=sign_in_failed", status_code=303)

    state_cookie = request.cookies.get(OAUTH_STATE_COOKIE)
    if not state_cookie:
        return RedirectResponse("/dashboard/admin/login?error=state_invalid", status_code=303)
    try:
        signed_state = _session_signer().loads(state_cookie, max_age=600)
    except (BadSignature, SignatureExpired, HTTPException):
        return RedirectResponse("/dashboard/admin/login?error=state_invalid", status_code=303)
    if not isinstance(signed_state, dict) or not secrets.compare_digest(
        str(signed_state.get("state", "")),
        state,
    ):
        return RedirectResponse("/dashboard/admin/login?error=state_invalid", status_code=303)
    code_verifier = signed_state.get("code_verifier")
    if not isinstance(code_verifier, str):
        return RedirectResponse("/dashboard/admin/login?error=state_invalid", status_code=303)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            token_response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.ADMIN_GOOGLE_CLIENT_ID,
                    "client_secret": settings.ADMIN_GOOGLE_CLIENT_SECRET,
                    "redirect_uri": settings.ADMIN_OAUTH_REDIRECT_URI,
                    "grant_type": "authorization_code",
                    "code_verifier": code_verifier,
                },
            )
            token_response.raise_for_status()
            token_data = token_response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Google sign-in could not be completed. Please try again.",
        ) from exc

    encoded_id_token = token_data.get("id_token") if isinstance(token_data, dict) else None
    if not isinstance(encoded_id_token, str):
        return RedirectResponse("/dashboard/admin/login?error=sign_in_failed", status_code=303)

    try:
        claims = id_token.verify_oauth2_token(
            encoded_id_token,
            GoogleAuthRequest(),
            settings.ADMIN_GOOGLE_CLIENT_ID,
        )
    except (ValueError, google_auth_exceptions.GoogleAuthError) as exc:
        raise HTTPException(
            status_code=401,
            detail="Google identity token could not be verified.",
        ) from exc

    email = claims.get("email")
    if (
        not isinstance(email, str)
        or email.casefold() != ALLOWED_ADMIN_EMAIL
        or claims.get("email_verified") is not True
    ):
        return RedirectResponse("/dashboard/admin/login?error=not_authorized", status_code=303)

    signed_session = _session_signer().dumps({"email": ALLOWED_ADMIN_EMAIL})
    response = RedirectResponse("/dashboard/admin", status_code=303)
    _set_auth_cookies(response, signed_session)
    return response


@router.post("/admin/auth/logout", include_in_schema=False)
async def admin_logout() -> Response:
    response = RedirectResponse("/dashboard/admin/login", status_code=303)
    response.delete_cookie(
        ADMIN_SESSION_COOKIE,
        httponly=True,
        secure=_secure_cookie(),
        samesite="lax",
        path="/",
    )
    return response


@api_router.get("/status")
async def admin_status(request: Request) -> dict[str, Any]:
    return {
        "authenticated": _admin_email_from_cookie(request) is not None,
        "sso_configured": _oauth_ready(),
        "allowed_admin_email": ALLOWED_ADMIN_EMAIL,
        "storage": {
            "provider": "firestore",
            "status": "not_connected",
            "configured": False,
            "editing_enabled": False,
        },
    }


@api_router.get("/overview")
async def admin_overview(request: Request) -> dict[str, Any]:
    email = _require_admin(request)
    try:
        knowledge_status = get_knowledge_base_status()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "admin_email": email,
        "knowledge_base": knowledge_status,
        "storage": {
            "provider": "firestore",
            "status": "not_connected",
            "configured": False,
            "editing_enabled": False,
        },
        "message": (
            "Admin sign-in is active. Editing is disabled until Firestore is "
            "connected with persistent storage."
        ),
    }
