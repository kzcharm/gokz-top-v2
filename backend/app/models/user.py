from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum
from typing import Literal

from sqlalchemy import BigInteger, Column, DateTime
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.dialects.postgresql import ARRAY
from sqlmodel import Field, Relationship, SQLModel

from .player import Player, PlayerRefPublic
from .utils import get_datetime_utc


def _enum_values(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


class UserRole(StrEnum):
    SUPERUSER = "superuser"
    MAP_ADMIN = "map_admin"
    SERVER_OWNER = "server_owner"


USER_ROLE_ORDER: tuple[UserRole, ...] = (
    UserRole.SUPERUSER,
    UserRole.MAP_ADMIN,
    UserRole.SERVER_OWNER,
)


def normalize_user_roles(
    roles: Iterable[UserRole | str] | None,
) -> list[UserRole]:
    if roles is None:
        return []

    role_set = {role if isinstance(role, UserRole) else UserRole(role) for role in roles}
    return [role for role in USER_ROLE_ORDER if role in role_set]


class UserBase(SQLModel):
    is_active: bool = True


class UserCreate(UserBase):
    steamid64: int = Field(sa_type=BigInteger)
    roles: list[UserRole] = Field(default_factory=list)


class UserUpdate(SQLModel):
    is_active: bool | None = None
    roles: list[UserRole] | None = None


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
    roles: list[UserRole] = Field(
        default_factory=list,
        sa_column=Column(
            ARRAY(
                SQLAlchemyEnum(
                    UserRole,
                    name="user_role",
                    values_callable=_enum_values,
                )
            ),
            nullable=False,
            default=list,
            server_default="{}",
        ),
    )
    player: Player | None = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[User.steamid64]", "uselist": False}
    )


class UserPublic(UserBase):
    steamid64: str
    roles: list[UserRole]
    created_at: datetime | None = None
    last_visited_at: datetime | None = None
    player: PlayerRefPublic | None = None


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int


class UsersListQuery(SQLModel):
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=100)
    sort_by: Literal["created_at", "last_visited_at"] = "created_at"
    sort_order: Literal["asc", "desc"] = "desc"
