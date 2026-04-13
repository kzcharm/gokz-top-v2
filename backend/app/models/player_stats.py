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
