from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime
from sqlmodel import Field, Relationship, SQLModel

from .player import Player, PlayerPublic
from .utils import get_datetime_utc

if TYPE_CHECKING:
    from .item import Item


class UserBase(SQLModel):
    is_active: bool = True
    is_superuser: bool = False


class UserCreate(UserBase):
    steamid64: int = Field(sa_type=BigInteger)


class UserUpdate(SQLModel):
    is_active: bool | None = None
    is_superuser: bool | None = None


class User(UserBase, table=True):
    steamid64: int = Field(
        primary_key=True,
        foreign_key="player.steamid64",
        sa_type=BigInteger,
    )
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    last_visited_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    player: Player | None = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[User.steamid64]", "uselist": False}
    )
    items: list[Item] = Relationship(back_populates="owner", cascade_delete=True)


class UserPublic(UserBase):
    steamid64: str
    created_at: datetime | None = None
    last_visited_at: datetime | None = None
    player: PlayerPublic | None = None


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int
