from bisect import bisect_right
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import field_serializer
from sqlalchemy import BigInteger, Column, DateTime, Index, text
from sqlalchemy import Enum as SqlEnum
from sqlmodel import Field, SQLModel

from .player import PlayerRefPublic
from .record import ModeScope, normalize_mode_scope
from .region import GeographyFilterMixin
from .utils import LegacyDatetimeNamesMixin, get_datetime_utc

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

_PUBLIC_RATING_SCALE = Decimal("2.5")
_PUBLIC_RATING_DIVISOR = Decimal("10000")
_PUBLIC_RATING_OFFSET = Decimal("1")
_PUBLIC_RATING_ANCHORS = (
    (1.14825, 1.0),
    (2.972, 2.0),
    (5.3625, 3.0),
    (7.5185, 4.0),
    (8.763, 5.0),
    (9.3665, 6.0),
    (9.6935, 7.0),
    (9.9585, 8.0),
    (10.22725, 9.0),
    (10.49825, 10.0),
    (11.0, 11.0),
)
_PUBLIC_RATING_ANCHOR_INPUTS = tuple(
    anchor_input for anchor_input, _anchor_output in _PUBLIC_RATING_ANCHORS
)
_PUBLIC_RATING_ANCHOR_OUTPUTS = tuple(
    anchor_output for _anchor_input, anchor_output in _PUBLIC_RATING_ANCHORS
)


def _pchip_endpoint_slope(
    *,
    h_this: float,
    h_other: float,
    delta_this: float,
    delta_other: float,
) -> float:
    slope = (
        ((2 * h_this) + h_other) * delta_this - h_this * delta_other
    ) / (h_this + h_other)
    if slope * delta_this <= 0:
        return 0.0
    if delta_this * delta_other < 0 and abs(slope) > abs(3 * delta_this):
        return 3 * delta_this
    return slope


def _build_public_rating_slopes() -> tuple[float, ...]:
    point_count = len(_PUBLIC_RATING_ANCHORS)
    if point_count < 2:
        return ()

    h_values = [
        _PUBLIC_RATING_ANCHOR_INPUTS[index + 1]
        - _PUBLIC_RATING_ANCHOR_INPUTS[index]
        for index in range(point_count - 1)
    ]
    deltas = [
        (_PUBLIC_RATING_ANCHOR_OUTPUTS[index + 1] - _PUBLIC_RATING_ANCHOR_OUTPUTS[index])
        / h_values[index]
        for index in range(point_count - 1)
    ]
    if point_count == 2:
        return (deltas[0], deltas[0])

    slopes = [0.0] * point_count
    slopes[0] = _pchip_endpoint_slope(
        h_this=h_values[0],
        h_other=h_values[1],
        delta_this=deltas[0],
        delta_other=deltas[1],
    )
    slopes[-1] = _pchip_endpoint_slope(
        h_this=h_values[-1],
        h_other=h_values[-2],
        delta_this=deltas[-1],
        delta_other=deltas[-2],
    )

    for index in range(1, point_count - 1):
        previous_delta = deltas[index - 1]
        next_delta = deltas[index]
        if previous_delta * next_delta <= 0:
            slopes[index] = 0.0
            continue
        h_previous = h_values[index - 1]
        h_next = h_values[index]
        weight_previous = 2 * h_next + h_previous
        weight_next = h_next + 2 * h_previous
        slopes[index] = (weight_previous + weight_next) / (
            (weight_previous / previous_delta) + (weight_next / next_delta)
        )

    return tuple(slopes)


_PUBLIC_RATING_SLOPES = _build_public_rating_slopes()


def redistribute_display_rating(value: float) -> float:
    clamped_value = min(
        max(value, _PUBLIC_RATING_ANCHOR_INPUTS[0]),
        _PUBLIC_RATING_ANCHOR_INPUTS[-1],
    )
    if clamped_value == _PUBLIC_RATING_ANCHOR_INPUTS[-1]:
        return _PUBLIC_RATING_ANCHOR_OUTPUTS[-1]

    segment_index = max(
        0,
        min(
            bisect_right(_PUBLIC_RATING_ANCHOR_INPUTS, clamped_value) - 1,
            len(_PUBLIC_RATING_ANCHORS) - 2,
        ),
    )
    x0 = _PUBLIC_RATING_ANCHOR_INPUTS[segment_index]
    x1 = _PUBLIC_RATING_ANCHOR_INPUTS[segment_index + 1]
    y0 = _PUBLIC_RATING_ANCHOR_OUTPUTS[segment_index]
    y1 = _PUBLIC_RATING_ANCHOR_OUTPUTS[segment_index + 1]
    slope0 = _PUBLIC_RATING_SLOPES[segment_index]
    slope1 = _PUBLIC_RATING_SLOPES[segment_index + 1]
    interval = x1 - x0
    position = (clamped_value - x0) / interval
    position_squared = position * position
    position_cubed = position_squared * position

    redistributed = (
        ((2 * position_cubed) - (3 * position_squared) + 1) * y0
        + (position_cubed - (2 * position_squared) + position) * interval * slope0
        + ((-2 * position_cubed) + (3 * position_squared)) * y1
        + (position_cubed - position_squared) * interval * slope1
    )
    return min(
        max(redistributed, _PUBLIC_RATING_ANCHOR_OUTPUTS[0]),
        _PUBLIC_RATING_ANCHOR_OUTPUTS[-1],
    )


def scale_public_rating(value: float | None) -> float | None:
    if value is None or value <= 0:
        return None

    old_rating = (Decimal(str(value)) * _PUBLIC_RATING_SCALE / _PUBLIC_RATING_DIVISOR) + (
        _PUBLIC_RATING_OFFSET
    )
    return redistribute_display_rating(float(old_rating))


class LeaderboardPlayerBase(LegacyDatetimeNamesMixin):
    scope: ModeScope = Field(
        sa_column=Column(
            SqlEnum(ModeScope, name="mode_scope"),
            primary_key=True,
            nullable=False,
        )
    )
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
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        validation_alias="updated_on",
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    def __init__(self, /, **data: object) -> None:
        payload = dict(data)
        if "scope" in payload:
            payload["scope"] = normalize_mode_scope(payload["scope"])
        super().__init__(**payload)


class LeaderboardPlayer(LeaderboardPlayerBase, table=True):
    __tablename__ = "leaderboard_player"
    __table_args__ = (
        Index(
            "ix_lb_player_scope_rating_order",
            "scope",
            text("rating DESC"),
            "steamid64",
        ),
        Index(
            "ix_lb_player_scope_rating_easy_order",
            "scope",
            text("rating_easy DESC"),
            text("rating DESC"),
            "steamid64",
        ),
        Index(
            "ix_lb_player_scope_rating_hard_order",
            "scope",
            text("rating_hard DESC"),
            text("rating DESC"),
            "steamid64",
        ),
        Index(
            "ix_lb_player_scope_points_order",
            "scope",
            text("points DESC"),
            text("rating DESC"),
            "steamid64",
        ),
        Index(
            "ix_lb_player_scope_wrs_nub_order",
            "scope",
            text("wrs_nub DESC"),
            text("rating DESC"),
            "steamid64",
        ),
        Index(
            "ix_lb_player_scope_wrs_pro_order",
            "scope",
            text("wrs_pro DESC"),
            text("rating DESC"),
            "steamid64",
        ),
        Index(
            "ix_lb_player_scope_900_order",
            "scope",
            text("records_900_plus DESC"),
            text("rating DESC"),
            "steamid64",
        ),
        Index(
            "ix_lb_player_scope_800_order",
            "scope",
            text("records_800_plus DESC"),
            text("rating DESC"),
            "steamid64",
        ),
        Index(
            "ix_lb_player_scope_unique_maps_order",
            "scope",
            text("unique_map_finishes DESC"),
            text("rating DESC"),
            "steamid64",
        ),
    )


class LeaderboardPlayerCount(LegacyDatetimeNamesMixin, table=True):
    __tablename__ = "leaderboard_player_count"

    scope: ModeScope = Field(
        sa_column=Column(
            SqlEnum(ModeScope, name="mode_scope"),
            primary_key=True,
            nullable=False,
        )
    )
    total: int = Field(default=0, ge=0)
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        validation_alias="updated_on",
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    def __init__(self, /, **data: object) -> None:
        payload = dict(data)
        if "scope" in payload:
            payload["scope"] = normalize_mode_scope(payload["scope"])
        super().__init__(**payload)


class PlayerLeaderboardEntryPublic(SQLModel):
    rank: int
    player: PlayerRefPublic
    rating: float | None
    rating_easy: float | None
    rating_hard: float | None
    points: int
    wrs_nub: int
    wrs_pro: int
    records_900_plus: int
    records_800_plus: int
    unique_map_finishes: int

    @field_serializer("rating", "rating_easy", "rating_hard")
    def serialize_rating(self, value: float | None) -> float | None:
        return scale_public_rating(value)


class PlayerLeaderboardRankPublic(SQLModel):
    scope: ModeScope
    rank: int | None = None
    rank_regional: int | None = None
    region: str | None = None
    player: PlayerRefPublic
    rating: float | None
    rating_easy: float | None
    rating_hard: float | None
    points: int
    wrs_nub: int
    wrs_pro: int
    records_900_plus: int
    records_800_plus: int
    unique_map_finishes: int

    @field_serializer("rating", "rating_easy", "rating_hard")
    def serialize_rating(self, value: float | None) -> float | None:
        return scale_public_rating(value)


class PlayerLeaderboardsPublic(SQLModel):
    data: list[PlayerLeaderboardEntryPublic]
    count: int


class PlayerLeaderboardListQuery(GeographyFilterMixin):
    scope: ModeScope = ModeScope.OVR
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)
    sort_by: LeaderboardPlayerSortBy = "rating"
    sort_order: Literal["desc"] = "desc"
    include_count: bool = True
