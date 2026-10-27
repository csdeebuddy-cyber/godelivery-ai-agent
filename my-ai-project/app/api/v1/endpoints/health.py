from fastapi import APIRouter

from app.config import settings

router = APIRouter()


@router.get("")
async def health_check() -> dict:
    return {
        "status": "ok",
        "service": "AI Agent Voice Allday",
        "version": "v1",
        "live_model": settings.GEMINI_LIVE_MODEL,
        "live_voice": settings.GEMINI_LIVE_VOICE,
        "max_context_tokens": settings.GEMINI_LIVE_MAX_CONTEXT_TOKENS,
        "target_context_tokens": settings.GEMINI_LIVE_TARGET_CONTEXT_TOKENS,
    }
