from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Column, DateTime
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from .mode_scope import ModeScope
from .record import RecordType
from .utils import get_datetime_utc


def _enum_values(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


class MapStatType(StrEnum):
    WR_GAP_DISTRIBUTION = "wr_gap_distribution"


class MapStatCache(SQLModel, table=True):
    __tablename__ = "map_stat"
    __table_args__ = {"schema": "cache"}

    map_id: int = Field(
        foreign_key="map.id",
        primary_key=True,
        ondelete="CASCADE",
    )
    scope: ModeScope = Field(
        sa_column=Column(
            SQLAlchemyEnum(
                ModeScope,
                name="mode_scope",
                values_callable=_enum_values,
            ),
            primary_key=True,
            nullable=False,
        ),
    )
    record_type: RecordType = Field(
        sa_column=Column(
            SQLAlchemyEnum(
                RecordType,
                name="record_type",
                values_callable=_enum_values,
            ),
            primary_key=True,
            nullable=False,
        ),
    )
    type: MapStatType = Field(
        sa_column=Column(
            SQLAlchemyEnum(
                MapStatType,
                name="map_stat_type",
                values_callable=_enum_values,
            ),
            primary_key=True,
            nullable=False,
        ),
    )
    content: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class MapWrGapDistributionBinPublic(SQLModel):
    label: str
    lower_bound: float | None = None
    upper_bound: float | None = None
    count: int = Field(default=0, ge=0)


class MapWrGapDistributionContentPublic(SQLModel):
    wr_time: float | None = Field(default=None, ge=0)
    median_wr_gap: float | None = None
    total_pb_count: int = Field(default=0, ge=0)
    plotted_pb_count: int = Field(default=0, ge=0)
    bins: list[MapWrGapDistributionBinPublic] = Field(default_factory=list)


class MapStatsPublic(SQLModel):
    map_id: int
    scope: ModeScope
    updated_at: datetime
    nub_wr_gap_distribution: MapWrGapDistributionContentPublic
    pro_wr_gap_distribution: MapWrGapDistributionContentPublic
