import unicodedata
from datetime import datetime
from typing import Literal

from pydantic import field_validator
from sqlalchemy import DateTime, Text
from sqlmodel import Field, SQLModel

from .utils import get_datetime_utc

PronunciationStatus = Literal["missing", "pending", "generating", "ready", "failed"]


class PronunciationFields(SQLModel):
    spoken_text: str = Field(sa_type=Text)
    source_text: str | None = Field(default=None, sa_type=Text)
    text_override: str | None = Field(default=None, sa_type=Text)
    voice_override: str | None = Field(default=None, max_length=100)
    language_code: str | None = Field(default=None, max_length=10)
    fingerprint: str = Field(max_length=64)
    status: str = Field(default="pending", max_length=20)
    object_key: str | None = Field(default=None, max_length=512)
    attempts: int = 0
    last_error: str | None = Field(default=None, max_length=100)
    next_attempt_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
    )
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
    )


class PronunciationPublic(SQLModel):
    status: PronunciationStatus
    spoken_text: str
    audio_url: str | None = None


class PronunciationRegenerate(SQLModel):
    model_config = {"extra": "forbid"}
    text: str = Field(min_length=1, max_length=500)
    voice_id: str = Field(min_length=1, max_length=100)
    language_code: str | None = Field(default=None, min_length=2, max_length=10)

    @field_validator("text")
    @classmethod
    def clean_text(cls, value: str) -> str:
        value = " ".join(value.replace("_", " ").split())
        if not value:
            raise ValueError("Enter text to speak")
        if any(unicodedata.category(character) == "Cc" for character in value):
            raise ValueError("Text must not contain control characters")
        return value

    @field_validator("voice_id", "language_code")
    @classmethod
    def clean_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Selection must not be blank")
        return value


class PronunciationAdminPublic(PronunciationPublic):
    source_text: str
    voice_id: str
    language_code: str | None = None


class PronunciationVoice(SQLModel):
    id: str
    name: str


class PronunciationLanguage(SQLModel):
    code: str
    name: str


class PronunciationOptions(SQLModel):
    voices: list[PronunciationVoice]
    languages: list[PronunciationLanguage]
    default_voice_id: str
