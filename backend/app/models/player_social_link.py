import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from .player import PlayerRefPublic
from .utils import generate_uuid7, get_datetime_utc


class PlayerSocialPlatform(StrEnum):
    BILIBILI = "bilibili"
    GITHUB = "github"
    TWITCH = "twitch"
    X = "x"
    YOUTUBE = "youtube"


class PlayerSocialLink(SQLModel, table=True):
    __tablename__ = "player_social_link"
    __table_args__ = (
        Index(
            "ux_player_social_link_player_platform",
            "player_steamid64",
            "platform",
            unique=True,
        ),
        Index(
            "ux_player_social_link_verified_account",
            "platform",
            "account_identifier",
            unique=True,
            postgresql_where=text("verified = true"),
        ),
    )

    id: uuid.UUID = Field(default_factory=generate_uuid7, primary_key=True)
    player_steamid64: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("player.steamid64", ondelete="CASCADE"),
            nullable=False,
        )
    )
    platform: PlayerSocialPlatform = Field(
        sa_column=Column(
            SqlEnum(PlayerSocialPlatform, name="player_social_platform"),
            nullable=False,
        )
    )
    account_identifier: str = Field(max_length=128, nullable=False)
    verified: bool = Field(default=False, nullable=False)
    show_on_site: bool = Field(default=True, nullable=False)
    metadata_json: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class PlayerSocialLinkCreate(SQLModel):
    url: str = Field(min_length=1, max_length=500)


class PlayerSocialLinkUpdate(SQLModel):
    url: str | None = Field(default=None, min_length=1, max_length=500)
    show_on_site: bool | None = None


class PlayerSocialLinkVerifyConfirm(SQLModel):
    pending_token: str = Field(min_length=1, max_length=4000)


class PlayerSocialLinkBilibiliVerificationStart(SQLModel):
    pending_token: str = Field(min_length=1, max_length=4000)
    verification_code: str = Field(min_length=1, max_length=128)
    profile_url: str = Field(min_length=1, max_length=500)
    current_profile_text: str = Field(max_length=2000)
    expires_at: datetime


class PlayerSocialLinkBilibiliProfileText(SQLModel):
    profile_text: str = Field(max_length=2000)


class AdminPlayerSocialLinkCreate(PlayerSocialLinkCreate):
    player_steamid64: str
    verified: bool = False


class AdminPlayerSocialLinkUpdate(SQLModel):
    url: str | None = Field(default=None, min_length=1, max_length=500)
    verified: bool | None = None


class PlayerSocialLinkPublic(SQLModel):
    id: uuid.UUID
    player_steamid64: str
    platform: PlayerSocialPlatform
    account_identifier: str
    verified: bool
    show_on_site: bool
    url: str
    created_at: datetime
    updated_at: datetime


class PlayerSocialLinksPublic(SQLModel):
    data: list[PlayerSocialLinkPublic]
    count: int


class AdminPlayerSocialLinkPublic(PlayerSocialLinkPublic):
    player: PlayerRefPublic | None = None


class AdminPlayerSocialLinksPublic(SQLModel):
    data: list[AdminPlayerSocialLinkPublic]
    count: int


class AdminPlayerSocialLinkListQuery(SQLModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)
    steamid64: str | None = None
    platform: PlayerSocialPlatform | None = None
    verified: bool | None = None
    sort_by: Literal["created_at", "updated_at", "platform"] = "created_at"
    sort_order: Literal["asc", "desc"] = "desc"
