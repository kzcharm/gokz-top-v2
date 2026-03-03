from datetime import datetime
from typing import Literal

from sqlalchemy import BigInteger, DateTime
from sqlmodel import Field, SQLModel

from .utils import get_datetime_utc


class PlayerBase(SQLModel):
    name: str = Field(max_length=255)
    alias: str | None = Field(default=None, max_length=25)
    custom_id: str | None = Field(default=None, max_length=25)
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
