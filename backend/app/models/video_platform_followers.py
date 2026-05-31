import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Text
from sqlalchemy import Enum as SqlEnum
from sqlmodel import Field, SQLModel

from .player_social_link import PlayerSocialPlatform
from .utils import get_datetime_utc


class PlayerVideoPlatformFollowerCache(SQLModel, table=True):
    __tablename__ = "player_video_platform_followers"
    __table_args__ = {"schema": "cache"}

    social_link_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("player_social_link.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        )
    )
    player_steamid64: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("player.steamid64", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    platform: PlayerSocialPlatform = Field(
        sa_column=Column(
            SqlEnum(PlayerSocialPlatform, name="player_social_platform"),
            nullable=False,
            index=True,
        )
    )
    account_identifier: str = Field(max_length=128, nullable=False)
    follower_count: int | None = Field(default=None, ge=0)
    fetched_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    last_attempted_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    error_message: str | None = Field(default=None, sa_column=Column(Text))


class VideoPlatformFollowerPublic(SQLModel):
    platform: PlayerSocialPlatform
    followers_count: int = Field(ge=0)
    url: str
    updated_at: datetime
