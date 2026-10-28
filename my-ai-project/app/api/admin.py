import base64
import hashlib
import json
import secrets
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, File, Header, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from google.api_core.exceptions import GoogleAPIError
from google.auth.exceptions import GoogleAuthError
from google.auth import exceptions as google_auth_exceptions
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings
from app.schemas.admin import GoogleSheetsSettings, ImageLinkImport
from app.schemas.site_content import SiteContent
from app.schemas.widget import WidgetSiteSettings
from app.services.admin_settings import (
    get_google_sheets_settings,
    save_google_sheets_settings,
)
from app.services.knowledge_base import get_knowledge_base_status
from app.services.google_sheets_knowledge import preview_google_sheets_knowledge
from app.services.site_content import get_site_content, save_site_content
from app.services.firebase.security import MAX_IMAGE_SIZE_BYTES, validate_catalog_image
from app.services.firebase.storage import list_catalog_images, upload_catalog_image
from app.services.firebase.image_import import ImageLinkError, import_catalog_image
from app.services.widget_sites import (
    delete_widget_site,
    get_widget_site,
    list_widget_sites,
    save_widget_site,
)


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


def _require_csrf(request: Request, csrf_token: str | None) -> None:
    signed_session = request.cookies.get(ADMIN_SESSION_COOKIE)
    if not signed_session or not settings.ADMIN_SESSION_SECRET:
        raise HTTPException(status_code=401, detail="Admin authentication required.")
    try:
        session = _session_signer().loads(
            signed_session,
            max_age=SESSION_MAX_AGE_SECONDS,
        )
    except (BadSignature, SignatureExpired, HTTPException) as exc:
        raise HTTPException(status_code=401, detail="Admin authentication required.") from exc
    expected_token = session.get("csrf_token") if isinstance(session, dict) else None
    if (
        not isinstance(expected_token, str)
        or not isinstance(csrf_token, str)
        or not secrets.compare_digest(expected_token, csrf_token)
    ):
        raise HTTPException(status_code=403, detail="Invalid CSRF token.")


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

    csrf_token = secrets.token_urlsafe(32)
    signed_session = _session_signer().dumps(
        {"email": ALLOWED_ADMIN_EMAIL, "csrf_token": csrf_token}
    )
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
    firestore_configured = bool(settings.FIRESTORE_PROJECT_ID)
    return {
        "authenticated": _admin_email_from_cookie(request) is not None,
        "sso_configured": _oauth_ready(),
        "allowed_admin_email": ALLOWED_ADMIN_EMAIL,
        "gemini_api_key_configured": bool(settings.GEMINI_API_KEY),
        "storage": {
            "provider": "firestore",
            "status": "configured" if firestore_configured else "not_configured",
            "configured": firestore_configured,
            "editing_enabled": firestore_configured,
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
        "csrf_token": _session_csrf_token(request),
        "gemini_api_key_configured": bool(settings.GEMINI_API_KEY),
        "knowledge_base": knowledge_status,
        "storage": {
            "provider": "firestore",
            "status": "configured" if settings.FIRESTORE_PROJECT_ID else "not_configured",
            "configured": bool(settings.FIRESTORE_PROJECT_ID),
            "editing_enabled": bool(settings.FIRESTORE_PROJECT_ID),
        },
        "firebase": {
            "project_id": settings.FIRESTORE_PROJECT_ID,
            "firestore_configured": bool(settings.FIRESTORE_PROJECT_ID),
            "storage_configured": bool(
                settings.FIRESTORE_PROJECT_ID and settings.FIREBASE_STORAGE_BUCKET
            ),
            "storage_bucket": settings.FIREBASE_STORAGE_BUCKET,
        },
        "message": "Homepage content is editable in Firestore; customer records are appended to private Google Sheets tabs."
        if settings.FIRESTORE_PROJECT_ID
        else "Website content cannot be published until Firestore and the Cloud Run service account are configured.",
    }


def _session_csrf_token(request: Request) -> str:
    signed_session = request.cookies.get(ADMIN_SESSION_COOKIE)
    if not signed_session:
        raise HTTPException(status_code=401, detail="Admin authentication required.")
    try:
        session = _session_signer().loads(
            signed_session,
            max_age=SESSION_MAX_AGE_SECONDS,
        )
    except (BadSignature, SignatureExpired, HTTPException) as exc:
        raise HTTPException(status_code=401, detail="Admin authentication required.") from exc
    csrf_token = session.get("csrf_token") if isinstance(session, dict) else None
    if not isinstance(csrf_token, str):
        raise HTTPException(status_code=401, detail="Admin session is missing CSRF protection.")
    return csrf_token


def _widget_site_response(site: dict[str, Any], base_url: str) -> dict[str, Any]:
    config = {
        "siteId": site["site_id"],
        "title": site["title"],
        "assistantName": site["assistant_name"],
        "launchText": site["launch_text"],
        "placeholder": site["placeholder"],
        "primaryColor": site["primary_color"],
        "speechLanguage": site["speech_language"],
        "voice": site["voice"],
    }
    config_json = (
        json.dumps(config, ensure_ascii=True, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    script_url = f"{base_url.rstrip('/')}/static/widget.js"
    embed_code = (
        "<script>\n"
        f"  window.GodeliveryChatConfig = {config_json};\n"
        "</script>\n"
        f'<script src="{script_url}" defer></script>'
    )
    return {
        "site_id": site["site_id"],
        "name": site["name"],
        "allowed_domains": site["allowed_domains"],
        "title": site["title"],
        "assistant_name": site["assistant_name"],
        "launch_text": site["launch_text"],
        "placeholder": site["placeholder"],
        "primary_color": site["primary_color"],
        "speech_language": site["speech_language"],
        "voice": site["voice"],
        "embed_code": embed_code,
    }


@api_router.get("/widget-sites")
def read_widget_sites(request: Request) -> dict[str, Any]:
    _require_admin(request)
    try:
        sites = list_widget_sites()
    except (RuntimeError, GoogleAPIError, GoogleAuthError) as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "firestore_unavailable",
                "message": "Widget sites are unavailable because Firestore is not configured or reachable.",
            },
        ) from exc
    return {
        "sites": [_widget_site_response(site, str(request.base_url)) for site in sites]
    }


@api_router.post("/widget-sites")
def create_widget_site(
    request: Request,
    configuration: WidgetSiteSettings,
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict[str, Any]:
    admin_email = _require_admin(request)
    _require_csrf(request, csrf_token)
    site_id = secrets.token_urlsafe(12)
    try:
        site = save_widget_site(
            site_id=site_id,
            configuration=configuration.model_dump(),
            created_by=admin_email,
        )
    except (RuntimeError, GoogleAPIError, GoogleAuthError) as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "firestore_unavailable",
                "message": "Widget site was not saved because Firestore is not configured or reachable.",
            },
        ) from exc
    return _widget_site_response(site, str(request.base_url))


@api_router.put("/widget-sites/{site_id}")
def update_widget_site(
    site_id: str,
    request: Request,
    configuration: WidgetSiteSettings,
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict[str, Any]:
    admin_email = _require_admin(request)
    _require_csrf(request, csrf_token)
    try:
        if get_widget_site(site_id) is None:
            raise HTTPException(status_code=404, detail="Widget site not found.")
        site = save_widget_site(
            site_id=site_id,
            configuration=configuration.model_dump(),
            created_by=admin_email,
        )
    except (RuntimeError, GoogleAPIError, GoogleAuthError) as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "firestore_unavailable",
                "message": "Widget site was not updated because Firestore is not configured or reachable.",
            },
        ) from exc
    return _widget_site_response(site, str(request.base_url))


@api_router.delete("/widget-sites/{site_id}", status_code=204)
def remove_widget_site(
    site_id: str,
    request: Request,
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> Response:
    _require_admin(request)
    _require_csrf(request, csrf_token)
    try:
        if get_widget_site(site_id) is None:
            raise HTTPException(status_code=404, detail="Widget site not found.")
        delete_widget_site(site_id)
    except (RuntimeError, GoogleAPIError, GoogleAuthError) as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "firestore_unavailable",
                "message": "Widget site was not removed because Firestore is not configured or reachable.",
            },
        ) from exc
    return Response(status_code=204)


@api_router.get("/settings/google-sheets")
def read_google_sheets_settings(request: Request) -> dict[str, Any]:
    _require_admin(request)
    try:
        return get_google_sheets_settings()
    except (RuntimeError, GoogleAPIError, GoogleAuthError) as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "firestore_unavailable",
                "message": "Google Sheets settings are not available because Firestore is not configured or reachable.",
            },
        ) from exc


@api_router.get("/settings/site-content")
def read_site_content(request: Request) -> dict[str, Any]:
    _require_admin(request)
    try:
        return get_site_content()
    except (RuntimeError, GoogleAPIError, GoogleAuthError) as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "firestore_unavailable",
                "message": "Website content is unavailable because Firestore is not configured or reachable.",
            },
        ) from exc


@api_router.put("/settings/site-content")
def update_site_content(
    request: Request,
    content: SiteContent,
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict[str, Any]:
    admin_email = _require_admin(request)
    _require_csrf(request, csrf_token)
    try:
        saved = save_site_content(content, updated_by=admin_email)
    except (RuntimeError, GoogleAPIError, GoogleAuthError) as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "firestore_unavailable",
                "message": "Website content was not saved because Firestore is not configured or reachable.",
            },
        ) from exc
    return {
        "status": "saved",
        "content": saved,
        "message": "บันทึกและเผยแพร่ข้อมูลหน้าเว็บไซต์แล้ว",
    }


@api_router.get("/assets")
def read_catalog_assets(request: Request) -> dict[str, Any]:
    _require_admin(request)
    try:
        return {"assets": list_catalog_images()}
    except (RuntimeError, GoogleAPIError, GoogleAuthError) as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "firebase_storage_unavailable",
                "message": "คลังภาพ Firebase ยังไม่พร้อมใช้งาน กรุณาตรวจการตั้งค่า Storage และสิทธิ์ service account",
            },
        ) from exc


@api_router.post("/assets/images", status_code=201)
async def upload_catalog_asset(
    request: Request,
    file: UploadFile = File(...),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict[str, Any]:
    admin_email = _require_admin(request)
    _require_csrf(request, csrf_token)
    try:
        data = await file.read(MAX_IMAGE_SIZE_BYTES + 1)
        if len(data) > MAX_IMAGE_SIZE_BYTES:
            raise HTTPException(status_code=413, detail="รูปภาพต้องมีขนาดไม่เกิน 5 MB")
        validate_catalog_image(data, file.content_type or "")
        return upload_catalog_image(
            data=data,
            content_type=file.content_type or "",
            filename=file.filename,
            uploaded_by=admin_email,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (RuntimeError, GoogleAPIError, GoogleAuthError) as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "firebase_storage_unavailable",
                "message": "อัปโหลดไม่สำเร็จ กรุณาตรวจ bucket และสิทธิ์ Storage ของ service account",
            },
        ) from exc
    finally:
        await file.close()


@api_router.post("/assets/import-link", status_code=201)
async def import_catalog_asset_link(
    request: Request,
    payload: ImageLinkImport,
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict[str, Any]:
    admin_email = _require_admin(request)
    _require_csrf(request, csrf_token)
    try:
        return await import_catalog_image(payload.url, admin_email)
    except (ImageLinkError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (RuntimeError, GoogleAPIError, GoogleAuthError) as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "firebase_storage_unavailable",
                "message": "บันทึกภาพไม่สำเร็จ กรุณาตรวจ bucket และสิทธิ์ Storage ของ service account",
            },
        ) from exc


@api_router.put("/settings/google-sheets")
def update_google_sheets_settings(
    request: Request,
    configuration: GoogleSheetsSettings,
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict[str, Any]:
    admin_email = _require_admin(request)
    _require_csrf(request, csrf_token)
    try:
        saved = save_google_sheets_settings(
            spreadsheet_id=configuration.spreadsheet_id,
            range_name=configuration.range,
            product_columns=configuration.product_columns.model_dump(),
            promotion_range=configuration.promotion_range,
            promotion_columns=configuration.promotion_columns.model_dump(),
            orders_range=configuration.orders_range,
            member_range=configuration.member_range,
            updated_by=admin_email,
        )
    except (RuntimeError, GoogleAPIError, GoogleAuthError) as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "firestore_unavailable",
                "message": "Settings were not saved because Firestore is not configured or reachable.",
            },
        ) from exc
    return {
        "status": "saved",
        "settings": saved,
        "message": "Spreadsheet settings saved. Use the preview action to read public product and promotion tabs; orders and MEMBER remain restricted.",
    }


@api_router.get("/settings/google-sheets/preview")
async def preview_google_sheets_settings(request: Request) -> dict[str, Any]:
    _require_admin(request)
    try:
        configuration = get_google_sheets_settings()
        if not configuration["configured"]:
            raise HTTPException(
                status_code=409,
                detail="Save Google Sheets settings before requesting a preview.",
            )
        return await preview_google_sheets_knowledge(configuration)
    except (RuntimeError, GoogleAPIError, GoogleAuthError) as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "google_sheets_unavailable",
                "message": "Google Sheets could not be read. Check Firestore, service account access, and the spreadsheet sharing settings.",
            },
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "google_sheets_request_failed",
                "message": "Google Sheets rejected the read request. Verify the spreadsheet ID, tab names, ranges, and service-account access.",
            },
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "google_sheets_preview_invalid",
                "message": str(exc),
            },
        ) from exc
