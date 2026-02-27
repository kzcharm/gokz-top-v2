import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime
from sqlmodel import Field, Relationship, SQLModel


def get_datetime_utc() -> datetime:
    return datetime.now(timezone.utc)


# Shared Player properties
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


# Database model, database table inferred from class name
class Player(PlayerBase, table=True):
    steamid64: int = Field(primary_key=True, sa_type=BigInteger)


# Properties to return via API
class PlayerPublic(PlayerBase):
    steamid64: str


class PlayersPublic(SQLModel):
    data: list[PlayerPublic]
    count: int


# Shared User properties
class UserBase(SQLModel):
    is_active: bool = True
    is_superuser: bool = False


# Properties to receive via API on creation
class UserCreate(UserBase):
    steamid64: int = Field(sa_type=BigInteger)


# Properties to receive via API on update, all are optional
class UserUpdate(SQLModel):
    is_active: bool | None = None
    is_superuser: bool | None = None


# Database model, database table inferred from class name
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
    items: list["Item"] = Relationship(back_populates="owner", cascade_delete=True)


# Properties to return via API, id is always required
class UserPublic(UserBase):
    steamid64: str
    created_at: datetime | None = None
    last_visited_at: datetime | None = None
    player: PlayerPublic | None = None


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int


# Shared properties
class ItemBase(SQLModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)


# Properties to receive on item creation
class ItemCreate(ItemBase):
    pass


# Properties to receive on item update
class ItemUpdate(ItemBase):
    title: str | None = Field(default=None, min_length=1, max_length=255)  # type: ignore


# Database model, database table inferred from class name
class Item(ItemBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    owner_id: int = Field(
        foreign_key="user.steamid64",
        nullable=False,
        ondelete="CASCADE",
        sa_type=BigInteger,
    )
    owner: User | None = Relationship(back_populates="items")


# Properties to return via API, id is always required
class ItemPublic(ItemBase):
    id: uuid.UUID
    owner_id: str
    created_at: datetime | None = None


class ItemsPublic(SQLModel):
    data: list[ItemPublic]
    count: int


# Generic message
class Message(SQLModel):
    message: str


# JSON payload containing access token
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


# Contents of JWT token
class TokenPayload(SQLModel):
    sub: str | None = None
