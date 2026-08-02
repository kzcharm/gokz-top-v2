from __future__ import annotations

import uuid as uuid_pkg
from datetime import datetime
from enum import StrEnum

from pydantic import AliasChoices
from sqlalchemy import BigInteger, Column, DateTime, Index, Text, text
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlmodel import Field, SQLModel

from .player import PlayerRefPublic
from .utils import LegacyDatetimeNamesMixin, generate_uuid7, get_datetime_utc


def _enum_values(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


class BanType(StrEnum):
    BAN_EVASION = "ban_evasion"
    BHOP_HACK = "bhop_hack"
    BHOP_MACRO = "bhop_macro"
    BOOSTING = "boosting"
    EXPLOITING = "exploiting"
    STRAFE_HACK = "strafe_hack"
    STRAFE_MACRO = "strafe_macro"
    OTHER = "other"


class BanStatus(StrEnum):
    PERMANENT = "permanent"
    ACTIVE = "active"
    EXPIRED = "expired"
    UNBANNED = "unbanned"


class BanBase(LegacyDatetimeNamesMixin):
    ban_type: BanType = Field(
        sa_column=Column(
            SQLAlchemyEnum(
                BanType,
                name="ban_type",
                values_callable=_enum_values,
            ),
            nullable=False,
        ),
    )
    expires_at: datetime | None = Field(  # type: ignore[call-overload]
        default=None,
        validation_alias=AliasChoices("expires_at", "expires_on"),
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
    ip: str | None = Field(default=None, max_length=64)
    steamid64: int = Field(foreign_key="player.steamid64", sa_type=BigInteger)
    notes: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    stats: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    server_id: int | None = None
    updated_by_steamid64: int | None = Field(
        default=None,
        validation_alias=AliasChoices("updated_by_steamid64", "updated_by_id"),
        sa_type=BigInteger,
    )
    created_at: datetime = Field(  # type: ignore[call-overload]
        default_factory=get_datetime_utc,
        validation_alias="created_on",
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
    updated_at: datetime = Field(  # type: ignore[call-overload]
        default_factory=get_datetime_utc,
        validation_alias="updated_on",
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
    synced_at: datetime = Field(  # type: ignore[call-overload]
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )


class Ban(BanBase, table=True):
    __tablename__ = "ban"  # type: ignore[assignment]
    __table_args__ = (
        Index(
            "uq_ban_external_id",
            "id",
            unique=True,
            postgresql_where=text("id IS NOT NULL"),
        ),
        Index("ix_ban_steamid64_expires_at", "steamid64", "expires_at"),
        Index("ix_ban_ban_type", "ban_type"),
        Index("ix_ban_server_id", "server_id"),
        Index("ix_ban_created_at", "created_at"),
        Index("ix_ban_updated_at", "updated_at"),
    )

    uuid: uuid_pkg.UUID = Field(default_factory=generate_uuid7, primary_key=True)
    id: int | None = Field(default=None)


class BanCreate(SQLModel):
    steamid64: str
    ban_type: BanType
    expires_at: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("expires_at", "expires_on"),
    )
    notes: str | None = None
    stats: str | None = None


class BanUpdate(SQLModel):
    ban_type: BanType
    expires_at: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("expires_at", "expires_on"),
    )
    notes: str | None = None


class BanCompatPublicV0(SQLModel):
    id: int
    ban_type: BanType
    expires_on: datetime | None = None
    ip: str | None = None
    steamid64: str
    player_name: str | None = None
    notes: str | None = None
    stats: str | None = None
    server_id: int | None = None
    updated_by_id: str | None = None
    created_on: datetime
    updated_on: datetime


class BanServerPublic(SQLModel):
    id: int
    name: str | None = None


class BanPublic(SQLModel):
    uuid: uuid_pkg.UUID
    id: int | None = None
    ban_type: BanType
    expires_at: datetime | None = None
    ip: str | None = None
    notes: str | None = None
    stats: str | None = None
    server_id: int | None = None
    updated_by_steamid64: str | None = None
    created_at: datetime
    updated_at: datetime
    player: PlayerRefPublic | None = None
    updated_by_player: PlayerRefPublic | None = None
    server: BanServerPublic | None = None


class BanListItemPublic(SQLModel):
    uuid: uuid_pkg.UUID
    id: int | None = None
    ban_type: BanType
    expires_at: datetime | None = None
    ip: str | None = None
    notes: str | None = None
    stats: str | None = None
    server_id: int | None = None
    updated_by_steamid64: str | None = None
    created_at: datetime
    updated_at: datetime
    player: PlayerRefPublic | None = None
    updated_by_player: PlayerRefPublic | None = None
    server: BanServerPublic | None = None


class BansPublic(SQLModel):
    data: list[BanListItemPublic]
    count: int


class BanListQuery(SQLModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=10000)
    q: str | None = Field(default=None, max_length=255)
    ban_types: str | None = None
    ban_types_list: list[str] | None = None
    is_expired: bool | None = None
    status: BanStatus | None = None
    ip: str | None = Field(default=None, max_length=64)
    steamid64: int | None = Field(default=None, sa_type=BigInteger)
    notes_contains: str | None = None
    stats_contains: str | None = None
    server_id: int | None = None
    has_server: bool | None = None
    created_since: datetime | None = None
    updated_since: datetime | None = None
