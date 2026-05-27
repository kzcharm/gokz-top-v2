import uuid
from datetime import datetime
from enum import StrEnum
from urllib.parse import urlsplit

from pydantic import ConfigDict, field_validator
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, text
from sqlalchemy import Enum as SqlEnum
from sqlmodel import Field, SQLModel

from .utils import generate_uuid7, get_datetime_utc


def _enum_values(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


def normalize_discord_webhook_url(url: str) -> str:
    normalized = url.strip()
    if not normalized:
        raise ValueError("Webhook URL cannot be blank")

    parsed = urlsplit(normalized)
    path = parsed.path.rstrip("/")
    if parsed.scheme != "https":
        raise ValueError("Webhook URL must use https")
    if not path.startswith("/api/webhooks/"):
        raise ValueError(
            "Webhook URL must use the Discord-compatible "
            "/api/webhooks/<id>/<token> format"
        )

    segments = [segment for segment in path.split("/") if segment]
    if len(segments) != 4 or segments[0] != "api" or segments[1] != "webhooks":
        raise ValueError(
            "Webhook URL must use the Discord-compatible "
            "/api/webhooks/<id>/<token> format"
        )
    if not segments[2].isdigit() or not segments[3]:
        raise ValueError(
            "Webhook URL must use the Discord-compatible "
            "/api/webhooks/<id>/<token> format"
        )

    if not parsed.hostname:
        raise ValueError("Webhook URL must include a host")

    normalized_host = parsed.hostname.lower()
    normalized_netloc = normalized_host
    if parsed.port is not None:
        normalized_netloc = f"{normalized_netloc}:{parsed.port}"

    normalized_url = (
        f"https://{normalized_netloc}/api/webhooks/{segments[2]}/{segments[3]}"
    )
    if parsed.query:
        normalized_url = f"{normalized_url}?{parsed.query}"
    return normalized_url


class PlayerWebhookProvider(StrEnum):
    DISCORD = "discord"


class PlayerWebhook(SQLModel, table=True):
    __tablename__ = "player_webhook"
    __table_args__ = (
        Index(
            "ux_player_webhook_owner_provider_url",
            "player_steamid64",
            "provider",
            "url",
            unique=True,
        ),
        Index("ix_player_webhook_owner_enabled", "player_steamid64", "enabled"),
    )

    id: uuid.UUID = Field(default_factory=generate_uuid7, primary_key=True)
    player_steamid64: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("player.steamid64", ondelete="CASCADE"),
            nullable=False,
        )
    )
    provider: PlayerWebhookProvider = Field(
        default=PlayerWebhookProvider.DISCORD,
        sa_column=Column(
            SqlEnum(
                PlayerWebhookProvider,
                name="player_webhook_provider",
                values_callable=_enum_values,
            ),
            nullable=False,
            server_default=text("'discord'"),
        ),
    )
    url: str = Field(max_length=500, nullable=False)
    enabled: bool = Field(default=True, nullable=False)
    last_used_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )


class PlayerWebhookCreate(SQLModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=500)

    @field_validator("url", mode="after")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return normalize_discord_webhook_url(value)


class PlayerWebhookUpdate(SQLModel):
    model_config = ConfigDict(extra="forbid")

    url: str | None = Field(default=None, min_length=1, max_length=500)
    enabled: bool | None = None

    @field_validator("url", mode="after")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_discord_webhook_url(value)


class PlayerWebhookPublic(SQLModel):
    id: uuid.UUID
    provider: PlayerWebhookProvider
    url: str
    enabled: bool
    last_used_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PlayerWebhooksPublic(SQLModel):
    data: list[PlayerWebhookPublic]
    count: int
