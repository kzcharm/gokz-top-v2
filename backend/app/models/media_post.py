import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Text
from sqlalchemy import Enum as SqlEnum
from sqlmodel import Field, SQLModel

from .player import PlayerRefPublic
from .player_social_link import PlayerSocialPlatform
from .utils import generate_uuid7, get_datetime_utc


class MediaPost(SQLModel, table=True):
    __tablename__ = "media_post"
    __table_args__ = (
        Index(
            "ux_media_post_platform_external_id",
            "platform",
            "external_video_id",
            unique=True,
        ),
        Index("ix_media_post_published_at_id", "published_at", "id"),
        Index("ix_media_post_player_published_at", "player_steamid64", "published_at"),
    )

    id: uuid.UUID = Field(default_factory=generate_uuid7, primary_key=True)
    player_social_link_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("player_social_link.id", ondelete="CASCADE"), nullable=False
        )
    )
    player_steamid64: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("player.steamid64", ondelete="CASCADE"),
            nullable=False,
        )
    )
    platform: PlayerSocialPlatform = Field(
        sa_column=Column(
            SqlEnum(PlayerSocialPlatform, name="player_social_platform"), nullable=False
        )
    )
    external_video_id: str = Field(max_length=128, nullable=False)
    title: str = Field(max_length=500, nullable=False)
    description: str | None = Field(default=None, sa_column=Column(Text))
    url: str = Field(max_length=500, nullable=False)
    thumbnail_url: str | None = Field(default=None, max_length=1000)
    published_at: datetime = Field(sa_type=DateTime(timezone=True))  # type: ignore
    view_count: int = Field(default=0, ge=0, nullable=False)
    discovered_at: datetime = Field(
        default_factory=get_datetime_utc, sa_type=DateTime(timezone=True)
    )  # type: ignore
    duration_seconds: int | None = Field(default=None, ge=0)
    available: bool = Field(default=True, nullable=False)
    last_checked_at: datetime = Field(
        default_factory=get_datetime_utc, sa_type=DateTime(timezone=True)
    )  # type: ignore
    last_error: str | None = Field(default=None, max_length=500)


class MediaPostPlayerPublic(PlayerRefPublic):
    pass


class MediaPostPublic(SQLModel):
    id: uuid.UUID
    player: MediaPostPlayerPublic
    platform: PlayerSocialPlatform
    external_video_id: str
    title: str
    description: str | None = None
    url: str
    thumbnail_url: str | None = None
    published_at: datetime
    view_count: int
    duration_seconds: int | None = None
    available: bool


class MediaPostsPublic(SQLModel):
    data: list[MediaPostPublic]
    next_cursor: str | None = None
    count: int


MediaPostSort = Literal["latest", "views", "length"]


class MediaPostsQuery(SQLModel):
    cursor: str | None = None
    limit: int = Field(default=24, ge=1, le=100)
    steamid64: str | None = None
    platform: Literal["youtube", "bilibili"] | None = None
    sort: MediaPostSort = "latest"
    from_: datetime | None = Field(default=None, alias="from")
    to: datetime | None = None


class MediaPostViewCountRefreshRequest(SQLModel):
    post_ids: list[uuid.UUID] = Field(min_length=1, max_length=24)


class MediaPostViewCountPublic(SQLModel):
    id: uuid.UUID
    view_count: int


class MediaPostViewCountsRefreshPublic(SQLModel):
    data: list[MediaPostViewCountPublic]
