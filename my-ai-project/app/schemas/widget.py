import re
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WidgetSiteSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=100)
    allowed_domains: list[str] = Field(..., min_length=1, max_length=20)
    title: str = Field(default="AI Agent Voice Allday", min_length=1, max_length=100)
    assistant_name: str = Field(default="AI Assistant", min_length=1, max_length=60)
    launch_text: str = Field(default="ถามเราได้เลย", min_length=1, max_length=60)
    placeholder: str = Field(
        default="พิมพ์ข้อความถึงเจ้าหน้าที่ AI...", min_length=1, max_length=100
    )
    primary_color: str = Field(default="#7c3aed", pattern=r"^#[0-9A-Fa-f]{6}$")
    speech_language: str = Field(default="th-TH", min_length=2, max_length=35)
    voice: str = Field(default="all-day", min_length=1, max_length=40)

    @field_validator("name", "title", "assistant_name", "launch_text", "placeholder")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("This field must not be blank.")
        return normalized

    @field_validator("allowed_domains")
    @classmethod
    def validate_domains(cls, domains: list[str]) -> list[str]:
        normalized_domains: list[str] = []
        for domain in domains:
            candidate = domain.strip().casefold().rstrip(".")
            parsed = urlsplit(f"//{candidate}")
            try:
                port = parsed.port
            except ValueError as exc:
                raise ValueError("Enter a valid website hostname and port.") from exc
            if (
                not candidate
                or parsed.hostname is None
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
                or not re.fullmatch(r"[a-z0-9.-]+(?::\d{1,5})?", candidate)
                or len(parsed.hostname) > 253
                or any(
                    not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part)
                    for part in parsed.hostname.split(".")
                )
                or (port is not None and not 1 <= port <= 65535)
            ):
                raise ValueError("Enter hostnames only, such as example.com.")
            if candidate not in normalized_domains:
                normalized_domains.append(candidate)
        if not normalized_domains:
            raise ValueError("At least one allowed domain is required.")
        return normalized_domains


class WidgetChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(..., min_length=1, max_length=4000)
    context: str | None = Field(default=None, max_length=4000)
    user_id: str | None = Field(default=None, max_length=200)
    voice: str = Field(default="all-day", min_length=1, max_length=40)
    speech_language: str = Field(default="th-TH", min_length=2, max_length=35)
