import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import field_validator, model_validator
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Numeric, text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from .mode_scope import ModeScope
from .player import PlayerRefPublic
from .record import KZMode
from .server import ServerGroupSummary
from .utils import generate_uuid7, get_datetime_utc


def _enum_values(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


def _decimal_to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


class JumpstatType(StrEnum):
    LJ = "LJ"
    BH = "BH"
    MBH = "MBH"
    WJ = "WJ"
    LAJ = "LAJ"
    LAH = "LAH"
    JB = "JB"
    LBH = "LBH"
    LWJ = "LWJ"
    FL = "FL"
    UNK = "UNK"
    INV = "INV"


class JumpstatStrafeStat(SQLModel):
    index: int = Field(ge=1)
    sync_percent: int = Field(ge=0, le=100)
    gain: float = Field(ge=0)
    loss: float = Field(ge=0)
    airtime_percent: int = Field(ge=0, le=100)
    width: float = Field(ge=0)
    overlap_count: int = Field(default=0, ge=0)
    dead_air_count: int = Field(default=0, ge=0)


def _normalize_strafe_stats(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("strafe_stats must be a list")

    normalized: list[dict[str, Any]] = []
    for item in value:
        stat = (
            item
            if isinstance(item, JumpstatStrafeStat)
            else JumpstatStrafeStat.model_validate(item)
        )
        normalized.append(stat.model_dump(mode="json"))
    return normalized


class Jumpstat(SQLModel, table=True):
    __tablename__ = "jumpstat"
    __table_args__ = (
        Index(
            "ix_jumpstat_type_mode_distance",
            "type",
            "mode",
            text("distance DESC"),
            text("jumped_at DESC"),
            text("id DESC"),
        ),
        Index(
            "ix_jumpstat_player_jumped_at",
            "player_steamid64",
            text("jumped_at DESC"),
            text("id DESC"),
        ),
        Index(
            "ix_jumpstat_group_jumped_at",
            "server_group_id",
            text("jumped_at DESC"),
            text("id DESC"),
        ),
        Index(
            "ix_jumpstat_block_distance",
            "block",
            text("distance DESC"),
            postgresql_where=text("block IS NOT NULL"),
        ),
    )

    id: uuid.UUID = Field(default_factory=generate_uuid7, primary_key=True)
    player_steamid64: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("player.steamid64", ondelete="CASCADE"),
            nullable=False,
        )
    )
    server_group_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("server_group.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    mode: KZMode = Field(
        sa_column=Column(
            SqlEnum(KZMode, name="kz_mode"),
            ForeignKey("mode.name_short"),
            nullable=False,
        )
    )
    type: JumpstatType = Field(
        sa_column=Column(
            SqlEnum(
                JumpstatType,
                name="jumpstat_type",
                values_callable=_enum_values,
            ),
            nullable=False,
        )
    )
    distance: Decimal = Field(sa_column=Column(Numeric(8, 4), nullable=False))
    block: int | None = Field(default=None, ge=0)
    strafes: int = Field(ge=1)
    sync_percent: int = Field(ge=0, le=100)
    pre_speed: Decimal = Field(sa_column=Column(Numeric(8, 4), nullable=False))
    max_speed: Decimal = Field(sa_column=Column(Numeric(8, 4), nullable=False))
    w_count: int = Field(default=0, ge=0)
    overlap_count: int = Field(default=0, ge=0)
    dead_air_count: int = Field(default=0, ge=0)
    width: Decimal = Field(sa_column=Column(Numeric(8, 4), nullable=False))
    height: Decimal = Field(sa_column=Column(Numeric(8, 4), nullable=False))
    airtime_percent: int = Field(ge=0, le=100)
    offset: Decimal = Field(sa_column=Column(Numeric(8, 4), nullable=False))
    crouched_ticks: int = Field(default=0, ge=0)
    edge: Decimal | None = Field(
        default=None,
        sa_column=Column(Numeric(8, 4), nullable=True),
    )
    deviation: Decimal | None = Field(
        default=None,
        sa_column=Column(Numeric(8, 4), nullable=True),
    )
    strafe_stats: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False),
    )
    jumped_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    @field_validator("strafe_stats", mode="before")
    @classmethod
    def _validate_strafe_stats(
        cls, value: list[dict[str, Any]] | list[JumpstatStrafeStat]
    ) -> list[dict[str, Any]]:
        return _normalize_strafe_stats(value)

    @model_validator(mode="after")
    def _validate_strafe_count(self) -> Jumpstat:
        if len(self.strafe_stats) != self.strafes:
            raise ValueError("strafes must match the number of strafe_stats entries")
        for expected_index, stat in enumerate(self.strafe_stats, start=1):
            if int(stat["index"]) != expected_index:
                raise ValueError("strafe_stats indexes must be sequential and 1-based")
        return self


class JumpstatPublic(SQLModel):
    id: uuid.UUID
    player: PlayerRefPublic
    server_group_id: uuid.UUID
    server_group: ServerGroupSummary
    mode: KZMode
    type: JumpstatType
    distance: float
    block: int | None = None
    strafes: int
    sync_percent: int
    pre_speed: float
    max_speed: float
    w_count: int
    overlap_count: int
    dead_air_count: int
    width: float
    height: float
    airtime_percent: int
    offset: float
    crouched_ticks: int
    edge: float | None = None
    deviation: float | None = None
    jumped_at: datetime
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(
        cls,
        *,
        jumpstat: Jumpstat,
        player: PlayerRefPublic,
        server_group: ServerGroupSummary,
    ) -> JumpstatPublic:
        return cls(
            id=jumpstat.id,
            player=player,
            server_group_id=jumpstat.server_group_id,
            server_group=server_group,
            mode=jumpstat.mode,
            type=jumpstat.type,
            distance=float(jumpstat.distance),
            block=jumpstat.block,
            strafes=jumpstat.strafes,
            sync_percent=jumpstat.sync_percent,
            pre_speed=float(jumpstat.pre_speed),
            max_speed=float(jumpstat.max_speed),
            w_count=jumpstat.w_count,
            overlap_count=jumpstat.overlap_count,
            dead_air_count=jumpstat.dead_air_count,
            width=float(jumpstat.width),
            height=float(jumpstat.height),
            airtime_percent=jumpstat.airtime_percent,
            offset=float(jumpstat.offset),
            crouched_ticks=jumpstat.crouched_ticks,
            edge=_decimal_to_float(jumpstat.edge),
            deviation=_decimal_to_float(jumpstat.deviation),
            jumped_at=jumpstat.jumped_at,
            created_at=jumpstat.created_at,
            updated_at=jumpstat.updated_at,
        )


class JumpstatDetailPublic(JumpstatPublic):
    strafe_stats: list[JumpstatStrafeStat]

    @classmethod
    def from_row(
        cls,
        *,
        jumpstat: Jumpstat,
        player: PlayerRefPublic,
        server_group: ServerGroupSummary,
    ) -> JumpstatDetailPublic:
        return cls(
            **JumpstatPublic.from_row(
                jumpstat=jumpstat,
                player=player,
                server_group=server_group,
            ).model_dump(),
            strafe_stats=[
                JumpstatStrafeStat.model_validate(stat) for stat in jumpstat.strafe_stats
            ],
        )


class JumpstatsPublic(SQLModel):
    data: list[JumpstatPublic]
    count: int


class JumpstatListQuery(SQLModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=1000)
    type: JumpstatType | None = None
    mode: KZMode | None = None
    block: int | None = Field(default=None, ge=0)
    server_group_id: uuid.UUID | None = None
    exclude_cheaters: bool = True
    sort_by: Literal["distance", "jumped_at", "created_at"] = "distance"
    sort_order: Literal["asc", "desc"] = "desc"


JumpstatLeaderboardSortBy = Literal["distance", "block"]


class JumpstatLeaderboardEntryPublic(SQLModel):
    rank: int
    id: uuid.UUID
    player: PlayerRefPublic
    server_group_id: uuid.UUID
    server_group: ServerGroupSummary
    mode: KZMode
    type: JumpstatType
    distance: float
    block: int | None = None
    strafes: int
    sync_percent: int
    pre_speed: float
    max_speed: float
    jumped_at: datetime

    @classmethod
    def from_row(
        cls,
        *,
        rank: int,
        jumpstat: Jumpstat,
        player: PlayerRefPublic,
        server_group: ServerGroupSummary,
    ) -> JumpstatLeaderboardEntryPublic:
        return cls(
            rank=rank,
            id=jumpstat.id,
            player=player,
            server_group_id=jumpstat.server_group_id,
            server_group=server_group,
            mode=jumpstat.mode,
            type=jumpstat.type,
            distance=float(jumpstat.distance),
            block=jumpstat.block,
            strafes=jumpstat.strafes,
            sync_percent=jumpstat.sync_percent,
            pre_speed=float(jumpstat.pre_speed),
            max_speed=float(jumpstat.max_speed),
            jumped_at=jumpstat.jumped_at,
        )


class JumpstatLeaderboardsPublic(SQLModel):
    data: list[JumpstatLeaderboardEntryPublic]
    count: int


class JumpstatLeaderboardListQuery(SQLModel):
    scope: ModeScope = ModeScope.OVR
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)
    type: JumpstatType = JumpstatType.LJ
    sort_by: JumpstatLeaderboardSortBy = "distance"
