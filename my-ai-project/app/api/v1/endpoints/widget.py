from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Query, Request, Response
from google.api_core.exceptions import GoogleAPIError
from google.auth.exceptions import GoogleAuthError

from app.config import settings
from app.schemas.chat import ChatResponse
from app.schemas.widget import WidgetChatRequest
from app.services.ai_service import AIService
from app.services.widget_sites import get_widget_site


router = APIRouter()


def _origin_for_site(request: Request, site_id: str) -> str:
    origin = request.headers.get("origin", "")
    parsed = urlsplit(origin)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise HTTPException(status_code=403, detail="This website is not allowed to use the chat widget.")

    try:
        site = get_widget_site(site_id)
    except (RuntimeError, GoogleAPIError, GoogleAuthError) as exc:
        raise HTTPException(
            status_code=503,
            detail="The chat widget is temporarily unavailable.",
        ) from exc
    if site is None:
        raise HTTPException(status_code=403, detail="This website is not allowed to use the chat widget.")

    allowed_domains = site.get("allowed_domains", [])
    origin_host = parsed.netloc.casefold().rstrip(".")
    if not isinstance(allowed_domains, list) or origin_host not in {
        str(domain).casefold().rstrip(".") for domain in allowed_domains
    }:
        raise HTTPException(status_code=403, detail="This website is not allowed to use the chat widget.")
    return origin


@router.options("/widget/chat")
async def widget_chat_preflight(
    request: Request,
    site_id: str = Query(..., pattern=r"^[A-Za-z0-9_-]{1,100}$"),
) -> Response:
    origin = _origin_for_site(request, site_id)
    return Response(
        status_code=204,
        headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Max-Age": "600",
            "Vary": "Origin",
        },
    )


@router.post("/widget/chat", response_model=ChatResponse)
async def widget_chat(
    payload: WidgetChatRequest,
    request: Request,
    response: Response,
    site_id: str = Query(..., pattern=r"^[A-Za-z0-9_-]{1,100}$"),
) -> ChatResponse:
    origin = _origin_for_site(request, site_id)
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Vary"] = "Origin"
    try:
        service = AIService()
        reply = await service.generate_response(payload.message, payload.context)
        return ChatResponse(
            reply=reply,
            voice=payload.voice,
            speech_language=payload.speech_language,
            model=settings.GEMINI_MODEL,
            status="success",
        )
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive fallback
        raise HTTPException(status_code=500, detail=f"AI request failed: {exc}") from exc
