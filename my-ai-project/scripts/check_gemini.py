"""Check whether the configured Gemini key and model can generate a response."""

import sys
from pathlib import Path

import google.generativeai as genai

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import Settings


def main() -> int:
    settings = Settings(_env_file=PROJECT_ROOT / ".env")
    api_key = settings.GEMINI_API_KEY

    if not api_key or api_key in {"your_gemini_api_key_here", "test-key"}:
        print("FAIL: GEMINI_API_KEY is missing or still a placeholder in .env.")
        return 1

    print(f"Checking Gemini model: {settings.GEMINI_MODEL}")
    genai.configure(api_key=api_key)

    try:
        model = genai.GenerativeModel(settings.GEMINI_MODEL)
        response = model.generate_content(
            "Reply with OK.",
            generation_config={"max_output_tokens": 32},
        )
    except Exception as exc:
        message = str(exc).lower()
        if "api_key_invalid" in message or "invalid api key" in message or "unauthorized" in message:
            print("FAIL: The API key was rejected. Check that the key is active and copied correctly.")
        elif "not found" in message or "not supported" in message:
            print("FAIL: The configured model is unavailable for this API/key. Check GEMINI_MODEL.")
        elif "resource_exhausted" in message or "quota" in message or "429" in message:
            print("FAIL: Gemini quota or billing is unavailable/exhausted for this project.")
        elif "permission_denied" in message or "billing" in message or "403" in message:
            print("FAIL: This project is not permitted to use Gemini. Check project access and billing.")
        else:
            print(f"FAIL: Gemini request failed ({type(exc).__name__}).")
        return 1

    try:
        response_text = response.text
    except ValueError:
        response_text = None

    if not response_text:
        print("FAIL: Gemini returned no text. Check the model response and safety settings.")
        return 1

    print("PASS: The key and model can generate a response.")
    print("Billing/quota was sufficient for this test request.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
