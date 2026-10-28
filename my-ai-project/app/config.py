from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "AI Agent Voice Allday"
    APP_ENV: str = "development"
    API_V1_STR: str = "/api/v1"
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-3.8-flash"
    GEMINI_LIVE_MODEL: str = "gemini-3.8-live"
    GEMINI_LIVE_VOICE: str = "Zephyr"
    GEMINI_LIVE_SYSTEM_INSTRUCTION: str = (
        "You are AI Agent Voice Allday, a helpful conversational assistant. "
        "Respond naturally and concisely in the user's language."
    )
    GEMINI_LIVE_MAX_CONTEXT_TOKENS: int = 104857
    FASAI_TRIAL_PRICE_THB: int = 290
    FASAI_CHECKOUT_VOICE_ENABLED: bool = False
    GEMINI_LIVE_TARGET_CONTEXT_TOKENS: int = 52428
    GEMINI_LIVE_MEDIA_RESOLUTION: str = "MEDIA_RESOLUTION_MEDIUM"
    ADMIN_GOOGLE_CLIENT_ID: str | None = None
    ADMIN_GOOGLE_CLIENT_SECRET: str | None = None
    ADMIN_OAUTH_REDIRECT_URI: str | None = None
    ADMIN_SESSION_SECRET: str | None = None
    # Member SSO falls back to the admin Google OAuth client and session secret.
    MEMBER_GOOGLE_CLIENT_ID: str | None = None
    MEMBER_GOOGLE_CLIENT_SECRET: str | None = None
    MEMBER_OAUTH_REDIRECT_URI: str | None = None
    MEMBER_SESSION_SECRET: str | None = None
    FIRESTORE_PROJECT_ID: str = "gen-lang-client-0845508747"
    FIREBASE_STORAGE_BUCKET: str | None = None
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


settings = Settings()
