from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    context: str | None = None
    user_id: str | None = None
    voice: str = "all-day"
    speech_language: str = Field(default="th-TH", min_length=2, max_length=35)


class ChatResponse(BaseModel):
    reply: str
    voice: str
    speech_language: str
    model: str
    status: str = "success"
