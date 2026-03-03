from datetime import datetime

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
