import os
from typing import Any

import google.generativeai as genai

from app.config import settings


class AIService:
    def __init__(self, model: str | None = None) -> None:
        self.model_name = model or settings.GEMINI_MODEL
        self.api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
        self.model = None

        if self.api_key and self.api_key not in {"your_gemini_api_key_here", "test-key"}:
            try:
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel(self.model_name)
            except Exception:
                self.model = None

    async def generate_response(self, message: str, context: str | None = None) -> str:
        if self.model is None:
            prefix = "Demo AI response"
            if context:
                return f"{prefix}: {message} (context: {context})"
            return f"{prefix}: {message}"

        prompt = message
        if context:
            prompt = f"Context: {context}\n\nUser: {message}"

        try:
            response = self.model.generate_content(prompt)
            return getattr(response, "text", str(response))
        except Exception:
            prefix = "Demo AI response"
            if context:
                return f"{prefix}: {message} (context: {context})"
            return f"{prefix}: {message}"

    async def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "model": self.model_name if self.model else "demo-mode",
        }
