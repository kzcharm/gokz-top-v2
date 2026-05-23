from datetime import datetime

from sqlalchemy import Column, DateTime
from sqlalchemy import Enum as SqlEnum
from sqlmodel import Field, SQLModel

from .map import MapRefPublic
from .map_review_summary import MapReviewSummaryPublic
from .record import ModeScope
from .utils import get_datetime_utc


class MapLeaderboardCache(SQLModel, table=True):
    __tablename__ = "map_leaderboard"
    __table_args__ = {"schema": "cache"}

    map_id: int = Field(
        foreign_key="map.id",
        primary_key=True,
        ondelete="CASCADE",
    )
    scope: ModeScope = Field(
        sa_column=Column(
            SqlEnum(ModeScope, name="mode_scope"),
            primary_key=True,
            nullable=False,
        )
    )
    total_finishes: int = Field(default=0, ge=0)
    total_playtime: float = Field(default=0, ge=0)
    average_first_completion_time: float = Field(default=0, ge=0)
    median_first_completion_time: float = Field(default=0, ge=0)
    average_playtime_per_player: float = Field(default=0, ge=0)
    median_playtime_per_player: float = Field(default=0, ge=0)
    average_finishes_per_player: float = Field(default=0, ge=0)
    median_finishes_per_player: float = Field(default=0, ge=0)
    pro_nub_ratio: float = Field(default=0, ge=0)
    unique_pro_finishes: int = Field(default=0, ge=0)
    unique_nub_finishes: int = Field(default=0, ge=0)
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class MapLeaderboardEntryPublic(SQLModel):
    map: MapRefPublic
    tier: int = 0
    review_summary: MapReviewSummaryPublic | None = None
    total_finishes: int
    total_playtime: float
    average_first_completion_time: float
    median_first_completion_time: float
    average_playtime_per_player: float
    median_playtime_per_player: float
    average_finishes_per_player: float
    median_finishes_per_player: float
    pro_nub_ratio: float
    unique_pro_finishes: int
    unique_nub_finishes: int
    updated_at: datetime | None = None


class MapLeaderboardsPublic(SQLModel):
    data: list[MapLeaderboardEntryPublic]
    count: int
