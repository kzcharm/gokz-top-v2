import re
from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import ConfigDict, field_validator
from sqlalchemy import BigInteger, Column, Computed, DateTime, Index, text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlmodel import Field, SQLModel

from .mode_scope import ModeScope
from .user_role import UserRole
from .utils import get_datetime_utc

MAX_PLAYER_CUSTOM_ID_LENGTH = 25
PLAYER_ALIAS_PATTERN = re.compile(r"^[A-Za-z0-9 _-]+$")
PLAYER_CUSTOM_ID_ALLOWED_PATTERN = re.compile(r"^[a-z0-9_-]+$")
PLAYER_CUSTOM_ID_PATTERN = re.compile(r"^[a-z0-9_-]*[a-z][a-z0-9_-]*$")


def _enum_values(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


class PlayerFriendsVisibility(StrEnum):
    PUBLIC = "public"
    PRIVATE_PROFILE = "private_profile"
    PRIVATE_FRIENDS = "private_friends"


def validate_player_custom_id(custom_id: str | None) -> str | None:
    if custom_id is None:
        return None

    normalized = custom_id.strip().lower()
    if not normalized:
        return None
    if len(normalized) > MAX_PLAYER_CUSTOM_ID_LENGTH:
        raise ValueError(
            f"custom_id must be at most {MAX_PLAYER_CUSTOM_ID_LENGTH} characters"
        )
    if not PLAYER_CUSTOM_ID_ALLOWED_PATTERN.fullmatch(normalized):
        raise ValueError(
            "custom_id can only use English letters, numbers, '-' or '_'"
        )
    if not PLAYER_CUSTOM_ID_PATTERN.fullmatch(normalized):
        raise ValueError(
            "custom_id must contain at least one English letter"
        )
    return normalized


def normalize_player_alias(alias: str | None) -> str | None:
    if alias is None:
        return None

    normalized = alias.strip()
    return normalized or None


def validate_player_settings_alias(alias: str | None) -> str | None:
    normalized = normalize_player_alias(alias)
    if normalized is None:
        return None
    if not PLAYER_ALIAS_PATTERN.fullmatch(normalized):
        raise ValueError(
            "alias can only use English letters, numbers, spaces, '-' or '_'"
        )
    return normalized


def normalize_player_country(country: str | None) -> str | None:
    if country is None:
        return None

    normalized = country.strip().upper()
    return normalized or None


class PlayerBase(SQLModel):
    model_config = ConfigDict(validate_assignment=True)

    name: str = Field(max_length=255)
    alias: str | None = Field(default=None, max_length=25)
    custom_id: str | None = Field(default=None, max_length=MAX_PLAYER_CUSTOM_ID_LENGTH)
    avatar_hash: str | None = Field(default=None, max_length=255)
    country: str | None = Field(default=None, max_length=2)
    primary_scope: ModeScope = Field(
        default=ModeScope.OVR,
        sa_column=Column(
            SqlEnum(ModeScope, name="mode_scope"),
            nullable=False,
            server_default=ModeScope.OVR.value,
        ),
    )
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    last_played_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    updated_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )

    @field_validator("custom_id", mode="after")
    @classmethod
    def _validate_custom_id(cls, value: str | None) -> str | None:
        return validate_player_custom_id(value)

    @field_validator("alias", mode="after")
    @classmethod
    def _normalize_alias(cls, value: str | None) -> str | None:
        return normalize_player_alias(value)

    @field_validator("country", mode="after")
    @classmethod
    def _normalize_country(cls, value: str | None) -> str | None:
        return normalize_player_country(value)


class Player(PlayerBase, table=True):
    __table_args__ = (
        Index(
            "ix_player_search_vector",
            "search_vector",
            postgresql_using="gin",
        ),
        Index(
            "ix_player_name_trgm",
            text("lower(name) gin_trgm_ops"),
            postgresql_using="gin",
        ),
        Index(
            "ix_player_alias_trgm",
            text("lower(coalesce(alias, '')) gin_trgm_ops"),
            postgresql_using="gin",
        ),
        Index(
            "ix_player_custom_id_trgm",
            text("lower(coalesce(custom_id, '')) gin_trgm_ops"),
            postgresql_using="gin",
        ),
        Index(
            "ux_player_custom_id_not_null",
            "custom_id",
            unique=True,
            postgresql_where=text("custom_id IS NOT NULL"),
        ),
        Index("ix_player_country_steamid64", "country", "steamid64"),
    )

    steamid64: int = Field(primary_key=True, sa_type=BigInteger)
    steam_profile_synced_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    friends_visibility: PlayerFriendsVisibility | None = Field(
        default=None,
        sa_column=Column(
            SqlEnum(
                PlayerFriendsVisibility,
                name="player_friends_visibility",
                values_callable=_enum_values,
            ),
            nullable=True,
        ),
    )
    friends_visibility_checked_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    search_vector: str | None = Field(
        default=None,
        sa_column=Column(
            TSVECTOR,
            Computed(
                """
                setweight(to_tsvector('simple', coalesce(custom_id, '')), 'A') ||
                setweight(to_tsvector('simple', coalesce(alias, '')), 'A') ||
                setweight(to_tsvector('simple', coalesce(name, '')), 'B')
                """,
                persisted=True,
            ),
            nullable=False,
        ),
    )


class PlayerPublic(PlayerBase):
    steamid64: str
    roles: list[UserRole] | None = None
    profile_views: int = 0


class PlayerDetailPublic(PlayerBase):
    steamid64: str
    roles: list[UserRole] | None = None


class PlayerRefPublic(SQLModel):
    steamid64: str
    display_name: str


class PlayersPublic(SQLModel):
    data: list[PlayerPublic]
    count: int


class PlayersListQuery(SQLModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)
    sort_by: Literal["created_at", "last_played_at"] = "created_at"
    sort_order: Literal["asc", "desc"] = "desc"


class PlayerSearchQuery(SQLModel):
    q: str = Field(min_length=1)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=50)

    @field_validator("q", mode="after")
    @classmethod
    def _validate_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("q must not be blank")
        return normalized


class PlayersBatchRead(SQLModel):
    steamid64s: list[str]


class PlayersBatchPublic(SQLModel):
    data: list[PlayerPublic | None]
    count: int


class PlayerProfileViewsPublic(SQLModel):
    profile_views: int = 0


class PlayerLikesPublic(SQLModel):
    player_likes: int = 0
    created: bool = False


class PlayerBanStatusCheckPublic(SQLModel):
    message: str
    cleared_ban_count: int = 0
    remaining_active_ban_count: int = 0


class PlayerProfileViewCreate(SQLModel):
    viewer_steamid64: str
    target_steamid64: str
    view_date: date


class PlayerUpdate(SQLModel):
    alias: str | None = Field(default=None, max_length=25)
    country: str | None = Field(default=None, max_length=2)
    primary_scope: ModeScope | None = None

    @field_validator("alias", mode="after")
    @classmethod
    def _normalize_alias(cls, value: str | None) -> str | None:
        return normalize_player_alias(value)

    @field_validator("country", mode="after")
    @classmethod
    def _normalize_country(cls, value: str | None) -> str | None:
        return normalize_player_country(value)
