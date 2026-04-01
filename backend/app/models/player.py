import re
from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, field_validator
from sqlalchemy import BigInteger, DateTime
from sqlmodel import Field, SQLModel

from .utils import get_datetime_utc

MAX_PLAYER_CUSTOM_ID_LENGTH = 25
PLAYER_CUSTOM_ID_PATTERN = re.compile(r"^[a-z0-9_-]*[a-z][a-z0-9_-]*$")


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
    if not PLAYER_CUSTOM_ID_PATTERN.fullmatch(normalized):
        raise ValueError(
            "custom_id must contain at least one letter and only use letters, numbers, '-' or '_'"
        )
    return normalized


class PlayerBase(SQLModel):
    model_config = ConfigDict(validate_assignment=True)

    name: str = Field(max_length=255)
    alias: str | None = Field(default=None, max_length=25)
    custom_id: str | None = Field(default=None, max_length=MAX_PLAYER_CUSTOM_ID_LENGTH)
    avatar_hash: str | None = Field(default=None, max_length=255)
    country: str | None = Field(default=None, max_length=2)
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


class Player(PlayerBase, table=True):
    steamid64: int = Field(primary_key=True, sa_type=BigInteger)


class PlayerPublic(PlayerBase):
    steamid64: str


class PlayersPublic(SQLModel):
    data: list[PlayerPublic]
    count: int


class PlayersListQuery(SQLModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)
    sort_by: Literal["created_at", "last_played_at"] = "created_at"
    sort_order: Literal["asc", "desc"] = "desc"


class PlayersBatchRead(SQLModel):
    steamid64s: list[str]


class PlayersBatchPublic(SQLModel):
    data: list[PlayerPublic | None]
    count: int


class PlayerUpdate(SQLModel):
    alias: str | None = Field(default=None, max_length=25)
    country: str | None = Field(default=None, max_length=2)
