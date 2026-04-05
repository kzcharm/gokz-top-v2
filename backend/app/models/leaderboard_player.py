from datetime import datetime
from typing import Literal

from sqlalchemy import BigInteger, Column, DateTime, Index, SmallInteger, text
from sqlmodel import Field, SQLModel

from .player import PlayerPublic
from .record import RecordScope
from .utils import get_datetime_utc

LeaderboardPlayerSortBy = Literal[
    "rating",
    "rating_easy",
    "rating_hard",
    "points",
    "wrs_nub",
    "wrs_pro",
    "records_900_plus",
    "records_800_plus",
    "unique_map_finishes",
]


class LeaderboardPlayerBase(SQLModel):
    scope: int = Field(sa_type=SmallInteger, primary_key=True)
    steamid64: int = Field(
        foreign_key="player.steamid64",
        sa_type=BigInteger,
        primary_key=True,
    )
    rating: int = Field(default=0, ge=0)
    rating_easy: int = Field(default=0, ge=0)
    rating_hard: int = Field(default=0, ge=0)
    points: int = Field(default=0, ge=0)
    wrs_nub: int = Field(default=0, ge=0)
    wrs_pro: int = Field(default=0, ge=0)
    records_900_plus: int = Field(default=0, ge=0)
    records_800_plus: int = Field(default=0, ge=0)
    unique_map_finishes: int = Field(default=0, ge=0)
    updated_on: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class LeaderboardPlayer(LeaderboardPlayerBase, table=True):
    __tablename__ = "leaderboard_player"
    __table_args__ = (
        Index(
            "ix_lb_player_scope_rating_pos",
            "scope",
            text("rating DESC"),
            "steamid64",
            postgresql_where=text("rating > 0"),
        ),
        Index(
            "ix_lb_player_scope_rating_easy_pos",
            "scope",
            text("rating_easy DESC"),
            "steamid64",
            postgresql_where=text("rating_easy > 0"),
        ),
        Index(
            "ix_lb_player_scope_rating_hard_pos",
            "scope",
            text("rating_hard DESC"),
            "steamid64",
            postgresql_where=text("rating_hard > 0"),
        ),
        Index(
            "ix_lb_player_scope_points_pos",
            "scope",
            text("points DESC"),
            "steamid64",
            postgresql_where=text("points > 0"),
        ),
        Index(
            "ix_lb_player_scope_wrs_nub_pos",
            "scope",
            text("wrs_nub DESC"),
            "steamid64",
            postgresql_where=text("wrs_nub > 0"),
        ),
        Index(
            "ix_lb_player_scope_wrs_pro_pos",
            "scope",
            text("wrs_pro DESC"),
            "steamid64",
            postgresql_where=text("wrs_pro > 0"),
        ),
        Index(
            "ix_lb_player_scope_900_pos",
            "scope",
            text("records_900_plus DESC"),
            "steamid64",
            postgresql_where=text("records_900_plus > 0"),
        ),
        Index(
            "ix_lb_player_scope_800_pos",
            "scope",
            text("records_800_plus DESC"),
            "steamid64",
            postgresql_where=text("records_800_plus > 0"),
        ),
        Index(
            "ix_lb_player_scope_unique_maps_pos",
            "scope",
            text("unique_map_finishes DESC"),
            "steamid64",
            postgresql_where=text("unique_map_finishes > 0"),
        ),
    )


class PlayerLeaderboardEntryPublic(SQLModel):
    rank: int
    player: PlayerPublic
    rating: int
    rating_easy: int
    rating_hard: int
    points: int
    wrs_nub: int
    wrs_pro: int
    records_900_plus: int
    records_800_plus: int
    unique_map_finishes: int


class PlayerLeaderboardRankPublic(SQLModel):
    scope: RecordScope
    rank: int | None = None
    rating_rank: int | None = None
    player: PlayerPublic
    rating: int
    rating_easy: int
    rating_hard: int
    points: int
    wrs_nub: int
    wrs_pro: int
    records_900_plus: int
    records_800_plus: int
    unique_map_finishes: int


class PlayerLeaderboardsPublic(SQLModel):
    data: list[PlayerLeaderboardEntryPublic]
    count: int


class PlayerLeaderboardListQuery(SQLModel):
    scope: RecordScope = RecordScope.OVR
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)
    sort_by: LeaderboardPlayerSortBy = "rating"
    sort_order: Literal["desc"] = "desc"
