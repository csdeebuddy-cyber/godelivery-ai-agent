import base64
import json
import hashlib
import logging
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from google.api_core.exceptions import GoogleAPIError
from google.auth import exceptions as google_auth_exceptions
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.schemas.member import BotReport, MemberProfileUpdate, PinSetupRequest, PinVerifyRequest
from app.services.members import security, service
from app.services.members.service import MemberError
from app.services.members.sheet_export import export_member


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/member", tags=["member"])
GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def _secure_cookie() -> bool:
    return settings.APP_ENV.casefold() in {"production", "prod"}


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _user_agent(request: Request) -> str:
    return request.headers.get("user-agent", "")


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, MemberError):
        return HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        )
    logger.error("Member storage unavailable: %s: %s", type(exc).__name__, exc)
    return HTTPException(
        status_code=503,
        detail={"code": "member_storage_unavailable", "message": "ระบบสมาชิกยังไม่พร้อมใช้งาน"},
    )


async def _run(func: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return await run_in_threadpool(func, *args, **kwargs)
    except (MemberError, GoogleAPIError, google_auth_exceptions.GoogleAuthError, RuntimeError) as exc:
        raise _http_error(exc) from exc


def read_session(request: Request) -> dict[str, Any] | None:
    session = security.read_signed(
        request.cookies.get(security.SESSION_COOKIE), security.SESSION_MAX_AGE_SECONDS
    )
    if session is None or not session.get("cn") or not session.get("did"):
        return None
    if session.get("stage") != "active" and time.time() - session.get("iat", 0) > security.PENDING_MAX_AGE_SECONDS:
        return None
    return session


def _issue_session(response: Response, customer_no: str, device_hash: str, stage: str) -> str:
    csrf = security.new_csrf_token()
    token = security.signer().dumps(
        {"cn": customer_no, "did": device_hash, "stage": stage, "csrf": csrf, "iat": time.time()}
    )
    response.set_cookie(
        security.SESSION_COOKIE,
        token,
        max_age=security.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=_secure_cookie(),
        samesite="lax",
        path="/",
    )
    return csrf


def _require(request: Request, stage: str) -> dict[str, Any]:
    session = read_session(request)
    if session is None:
        raise HTTPException(401, {"code": "unauthenticated", "message": "กรุณาเข้าสู่ระบบ"})
    supplied = request.headers.get("x-csrf-token", "")
    if not secrets.compare_digest(str(session.get("csrf", "")), supplied):
        raise HTTPException(403, {"code": "csrf_invalid", "message": "Invalid CSRF token."})
    if session.get("stage") != stage:
        raise HTTPException(409, {"code": "wrong_stage", "message": "ขั้นตอนไม่ถูกต้อง"})
    return session


async def _bot_lock(request: Request, session: dict[str, Any], signal: str) -> HTTPException:
    await _run(
        service.lock_for_bot,
        device_hash=session["did"],
        customer_no=session["cn"],
        signal=signal,
        user_agent=_user_agent(request),
        ip=_client_ip(request),
    )
    member = await _run(service.load_member_unchecked, session["cn"])
    if member:
        await export_member(member, f"bot_locked:{signal}")
    return HTTPException(
        423, {"code": "account_locked", "message": "บัญชีนี้ถูกล็อคเพื่อความปลอดภัย กรุณาติดต่อเจ้าหน้าที่"}
    )


@router.get("/auth/google/login", include_in_schema=False)
async def member_google_login(request: Request, device_id: str = "") -> Response:
    config = security.oauth_config()
    if config is None:
        return RedirectResponse("/?member_error=sso_not_configured", status_code=303)
    if not security.DEVICE_ID_PATTERN.fullmatch(device_id):
        return RedirectResponse("/?member_error=invalid_device", status_code=303)
    if security.looks_like_bot(_user_agent(request)):
        await _run(
            service.lock_for_bot,
            device_hash=security.hash_device_id(device_id),
            customer_no=None,
            signal="user_agent",
            user_agent=_user_agent(request),
            ip=_client_ip(request),
        )
        return RedirectResponse("/?member_error=account_locked", status_code=303)

    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    query = urlencode(
        {
            "client_id": config["client_id"],
            "redirect_uri": config["redirect_uri"],
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
    )
    response = RedirectResponse(f"{GOOGLE_AUTHORIZE_URL}?{query}", status_code=302)
    response.set_cookie(
        security.OAUTH_STATE_COOKIE,
        security.signer().dumps(
            {"state": state, "code_verifier": code_verifier, "device_id": device_id}
        ),
        max_age=600,
        httponly=True,
        secure=_secure_cookie(),
        samesite="lax",
        path="/",
    )
    return response


@router.get("/auth/google/callback", include_in_schema=False)
async def member_google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Response:
    def fail(reason: str) -> Response:
        response = RedirectResponse(f"/?member_error={reason}", status_code=303)
        response.delete_cookie(security.OAUTH_STATE_COOKIE, path="/")
        return response

    config = security.oauth_config()
    if error or not code or not state or config is None:
        return fail("sign_in_failed")
    saved = security.read_signed(request.cookies.get(security.OAUTH_STATE_COOKIE), 600)
    if (
        saved is None
        or not secrets.compare_digest(str(saved.get("state", "")), state)
        or not security.DEVICE_ID_PATTERN.fullmatch(str(saved.get("device_id", "")))
    ):
        return fail("state_invalid")

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            token_response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": config["client_id"],
                    "client_secret": config["client_secret"],
                    "redirect_uri": config["redirect_uri"],
                    "grant_type": "authorization_code",
                    "code_verifier": saved["code_verifier"],
                },
            )
            token_response.raise_for_status()
            encoded = token_response.json().get("id_token")
        claims = id_token.verify_oauth2_token(encoded, GoogleAuthRequest(), config["client_id"])
    except (httpx.HTTPError, ValueError, google_auth_exceptions.GoogleAuthError):
        return fail("sign_in_failed")

    email = claims.get("email")
    if not isinstance(email, str) or claims.get("email_verified") is not True:
        return fail("email_unverified")

    try:
        member, device_hash, stage, created = await run_in_threadpool(
            service.sign_in_with_google,
            email=email,
            name=str(claims.get("name", ""))[:160],
            device_id=saved["device_id"],
            user_agent=_user_agent(request),
            ip=_client_ip(request),
        )
    except MemberError as exc:
        return fail(exc.code)
    except (GoogleAPIError, google_auth_exceptions.GoogleAuthError, RuntimeError):
        logger.exception("Member sign-in storage failure.")
        return fail("member_storage_unavailable")

    if created:
        await export_member(member, "signup")
    response = RedirectResponse(f"/?member={stage}", status_code=303)
    _issue_session(response, member["customer_no"], device_hash, stage)
    response.delete_cookie(security.OAUTH_STATE_COOKIE, path="/")
    return response


@router.get("/me")
async def member_me(request: Request, response: Response) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    session = read_session(request)
    if session is None:
        return {"authenticated": False, "sso_configured": security.oauth_config() is not None}
    try:
        member = await run_in_threadpool(service.load_member, session["cn"], session["did"])
    except MemberError as exc:
        return {"authenticated": False, "error": exc.code}
    except (GoogleAPIError, google_auth_exceptions.GoogleAuthError, RuntimeError) as exc:
        raise _http_error(exc) from exc
    body: dict[str, Any] = {
        "authenticated": True,
        "stage": session["stage"],
        "csrf_token": session["csrf"],
        "customer_no": member["customer_no"],
        "email": member["email"],
    }
    if session["stage"] == "active":
        body["profile"] = service.public_profile(member)
    return body


@router.post("/pin/setup")
async def member_pin_setup(payload: PinSetupRequest, request: Request) -> Response:
    session = _require(request, "setup_pin")
    if payload.website:
        raise await _bot_lock(request, session, "honeypot")
    member = await _run(
        service.set_pin, session["cn"], session["did"], payload.pin, payload.confirm_pin
    )
    response = Response()
    csrf = _issue_session(response, member["customer_no"], session["did"], "active")
    return _json_with_cookie(response, {"stage": "active", "csrf_token": csrf})


@router.post("/pin/verify")
async def member_pin_verify(payload: PinVerifyRequest, request: Request) -> Response:
    session = _require(request, "verify_pin")
    if payload.website:
        raise await _bot_lock(request, session, "honeypot")
    member = await _run(service.check_pin, session["cn"], session["did"], payload.pin)
    response = Response()
    csrf = _issue_session(response, member["customer_no"], session["did"], "active")
    return _json_with_cookie(response, {"stage": "active", "csrf_token": csrf})


@router.put("/profile")
async def member_update_profile(payload: MemberProfileUpdate, request: Request) -> dict[str, Any]:
    session = _require(request, "active")
    if payload.website:
        raise await _bot_lock(request, session, "honeypot")
    member = await _run(
        service.update_profile,
        session["cn"],
        session["did"],
        payload.model_dump(exclude={"website"}),
    )
    await export_member(member, "profile_update")
    return {"profile": service.public_profile(member)}


@router.post("/security/bot-report")
async def member_bot_report(payload: BotReport, request: Request) -> dict[str, str]:
    session = read_session(request)
    if session is not None and session["did"] == security.hash_device_id(payload.device_id):
        raise await _bot_lock(request, session, payload.signal)
    await _run(
        service.lock_for_bot,
        device_hash=security.hash_device_id(payload.device_id),
        customer_no=None,
        signal=payload.signal,
        user_agent=_user_agent(request),
        ip=_client_ip(request),
    )
    return {"status": "blocked"}


@router.post("/logout")
async def member_logout() -> Response:
    response = Response(status_code=204)
    response.delete_cookie(security.SESSION_COOKIE, path="/")
    return response


def _json_with_cookie(cookie_source: Response, body: dict[str, Any]) -> Response:
    response = Response(content=json.dumps(body), media_type="application/json")
    for header in cookie_source.headers.getlist("set-cookie"):
        response.headers.append("set-cookie", header)
    return response
