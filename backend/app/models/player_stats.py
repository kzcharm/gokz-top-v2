from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, Column, DateTime
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from .utils import get_datetime_utc


def _enum_values(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


class PlayerStatType(StrEnum):
    DAILY_ACTIVITY = "daily_activity"
    PLAYTIME = "playtime"


class PlayerStatCache(SQLModel, table=True):
    __tablename__ = "player_stats"
    __table_args__ = {"schema": "cache"}

    steamid64: int = Field(
        foreign_key="player.steamid64",
        primary_key=True,
        ondelete="CASCADE",
        sa_type=BigInteger,
    )
    type: PlayerStatType = Field(
        sa_column=Column(
            SQLAlchemyEnum(
                PlayerStatType,
                name="player_stat_type",
                values_callable=_enum_values,
            ),
            primary_key=True,
            nullable=False,
        )
    )
    content: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class PlayerDailyActivityDayPublic(SQLModel):
    date: date
    count: int = Field(ge=0)


class PlayerDailyActivityContentPublic(SQLModel):
    days: list[PlayerDailyActivityDayPublic] = Field(default_factory=list)


class PlayerDailyActivityStatPublic(SQLModel):
    steamid64: str
    type: PlayerStatType
    updated_at: datetime
    content: PlayerDailyActivityContentPublic


class PlayerPlaytimeCursor(SQLModel):
    latest_day: date | None = None
    total_before_latest_day: float = Field(default=0, ge=0)


class PlayerPlaytimeContentPublic(SQLModel):
    total_seconds: float = Field(default=0, ge=0)


class PlayerPlaytimeCacheContent(PlayerPlaytimeContentPublic):
    cursor: PlayerPlaytimeCursor | None = None


class PlayerPlaytimeStatPublic(SQLModel):
    steamid64: str
    type: PlayerStatType
    updated_at: datetime
    content: PlayerPlaytimeContentPublic


class PlayerDailyActivityPublic(SQLModel):
    updated_at: datetime
    days: list[PlayerDailyActivityDayPublic] = Field(default_factory=list)


class PlayerPlaytimePublic(SQLModel):
    updated_at: datetime
    total_seconds: float = Field(default=0, ge=0)


class PlayerStatsPublic(SQLModel):
    steamid64: str
    daily_activity: PlayerDailyActivityPublic | None = None
    playtime: PlayerPlaytimePublic | None = None
