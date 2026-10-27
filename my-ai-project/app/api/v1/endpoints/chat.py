from fastapi import APIRouter, HTTPException

from app.config import settings
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.ai_service import AIService

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat_with_ai(payload: ChatRequest) -> ChatResponse:
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
