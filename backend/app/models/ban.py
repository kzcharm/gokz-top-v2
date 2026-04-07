from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, Index, Text
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlmodel import Column, Field, SQLModel

from .player import PlayerPublic
from .utils import get_datetime_utc


def _enum_values(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


class BanType(StrEnum):
    BAN_EVASION = "ban_evasion"
    BHOP_HACK = "bhop_hack"
    BHOP_MACRO = "bhop_macro"
    EXPLOITING = "exploiting"
    STRAFE_HACK = "strafe_hack"
    STRAFE_MACRO = "strafe_macro"
    OTHER = "other"


class BanBase(SQLModel):
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
    expires_on: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
    ip: str | None = Field(default=None, max_length=64)
    steamid64: int = Field(sa_type=BigInteger)
    player_name: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    stats: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    server_id: int | None = None
    updated_by_id: str | None = Field(default=None, max_length=32)
    created_on: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
    updated_on: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
    synced_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )


class Ban(BanBase, table=True):
    __tablename__ = "ban"  # type: ignore[assignment]
    __table_args__ = (
        Index("ix_ban_steamid64_expires_on", "steamid64", "expires_on"),
        Index("ix_ban_ban_type", "ban_type"),
        Index("ix_ban_server_id", "server_id"),
        Index("ix_ban_created_on", "created_on"),
        Index("ix_ban_updated_on", "updated_on"),
    )

    id: int = Field(primary_key=True)


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


class BanPublic(BanCompatPublicV0):
    player: PlayerPublic | None = None


class BansPublic(SQLModel):
    data: list[BanPublic]
    count: int


class BanListQuery(SQLModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=10000)
    ban_types: str | None = None
    ban_types_list: list[str] | None = None
    is_expired: bool | None = None
    ip: str | None = Field(default=None, max_length=64)
    steamid64: int | None = Field(default=None, sa_type=BigInteger)
    notes_contains: str | None = None
    stats_contains: str | None = None
    server_id: int | None = None
    created_since: datetime | None = None
    updated_since: datetime | None = None
