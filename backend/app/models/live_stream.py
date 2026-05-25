import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index
from sqlmodel import Field, SQLModel

from .player_social_link import PlayerSocialPlatform
from .user_role import UserRole
from .utils import get_datetime_utc


class LiveStreamState(SQLModel, table=True):
    __tablename__ = "live_stream_state"  # type: ignore[assignment]
    __table_args__ = (
        Index("ix_live_stream_state_is_live", "is_live"),
        Index("ix_live_stream_state_last_checked_at", "last_checked_at"),
        Index("ix_live_stream_state_last_live_seen_at", "last_live_seen_at"),
    )

    social_link_id: uuid.UUID = Field(
        foreign_key="player_social_link.id",
        primary_key=True,
        ondelete="CASCADE",
    )
    last_checked_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
    is_live: bool = Field(default=False, nullable=False)
    last_live_started_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
    last_live_seen_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
    last_stream_url: str | None = Field(default=None, max_length=500)
    last_stream_title: str | None = Field(default=None, max_length=255)
    last_preview_image_url: str | None = Field(default=None, max_length=1000)
    last_keyframe_image_url: str | None = Field(default=None, max_length=1000)
    last_channel_display_name: str | None = Field(default=None, max_length=255)
    last_viewer_count: int | None = Field(default=None, ge=0)
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )


class LiveStreamPlayerPublic(SQLModel):
    steamid64: str
    name: str
    alias: str | None = None
    avatar_hash: str | None = None
    country: str | None = None
    custom_id: str | None = None
    roles: list[UserRole] | None = None


class LiveStreamCardPublic(SQLModel):
    player: LiveStreamPlayerPublic
    selected_platform: PlayerSocialPlatform
    selected_platform_account_identifier: str
    is_live: bool
    stream_url: str
    last_viewer_count: int | None = None
    preview_image_url: str | None = None
    hover_preview_image_url: str | None = None
    stream_title: str | None = None
    started_at: datetime | None = None
    last_streamed_at: datetime | None = None


class LiveStreamsPublic(SQLModel):
    data: list[LiveStreamCardPublic]
    count: int


class LiveStreamListQuery(SQLModel):
    online: bool | None = None
