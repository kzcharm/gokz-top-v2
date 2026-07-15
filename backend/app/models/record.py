import uuid
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Literal

from pydantic import model_validator
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    text,
)
from sqlalchemy import Enum as SqlEnum
from sqlmodel import Field, SQLModel

from .mode_scope import (
    ModeScope,
    mode_scope_mode_ids,
    mode_scope_to_id,
    normalize_mode_scope,
)
from .player import PlayerRefPublic
from .server import ServerGroupSummary
from .server_globalapi import ServerGlobalapiCompatPublicV0
from .utils import LegacyDatetimeNamesMixin, generate_uuid7, get_datetime_utc


class TeleportsType(StrEnum):
    PRO = "PRO"
    NUB = "NUB"
    OVR = "OVR"


class KZMode(StrEnum):
    KZT = "KZT"
    SKZ = "SKZ"
    VNL = "VNL"
    NKZ = "NKZ"

    @property
    def mode_id(self) -> int:
        return LEGACY_MODE_ID_BY_KZ_MODE[self]


class RecordType(StrEnum):
    NUB = "NUB"
    PRO = "PRO"

    @property
    def is_pro(self) -> bool:
        return self is RecordType.PRO


LEGACY_MODE_ID_BY_KZ_MODE: dict[KZMode, int] = {
    KZMode.KZT: 200,
    KZMode.SKZ: 201,
    KZMode.VNL: 202,
    KZMode.NKZ: 203,
}

KZ_MODE_BY_LEGACY_MODE_ID: dict[int, KZMode] = {
    legacy_id: mode for mode, legacy_id in LEGACY_MODE_ID_BY_KZ_MODE.items()
}

MODE_SCOPE_MODE_IDS: dict[int, tuple[int, ...]] = {
    mode_scope_to_id(scope): mode_scope_mode_ids(mode_scope_to_id(scope))
    for scope in ModeScope
}

def legacy_mode_id_to_kz_mode(mode_id: int) -> KZMode:
    return KZ_MODE_BY_LEGACY_MODE_ID[mode_id]


def kz_mode_to_legacy_mode_id(mode: KZMode) -> int:
    return LEGACY_MODE_ID_BY_KZ_MODE[mode]


def _normalize_record_payload(data: dict[str, object]) -> dict[str, object]:
    payload = dict(data)
    if "mode" not in payload and "mode_id" in payload:
        payload["mode"] = normalize_kz_mode(payload.pop("mode_id"))
    elif "mode" in payload:
        payload["mode"] = normalize_kz_mode(payload["mode"])
    return payload


def _normalize_record_pb_payload(data: dict[str, object]) -> dict[str, object]:
    payload = dict(data)
    if "scope" in payload:
        payload["scope"] = normalize_mode_scope(payload["scope"])
    if "type" not in payload and "is_pro_only" in payload:
        payload["type"] = normalize_record_type(payload.pop("is_pro_only"))
    elif "type" in payload:
        payload["type"] = normalize_record_type(payload["type"])
    return payload


def normalize_kz_mode(value: KZMode | str | int) -> KZMode:
    if isinstance(value, KZMode):
        return value
    if isinstance(value, int):
        return legacy_mode_id_to_kz_mode(value)
    return KZMode(value)


def normalize_record_type(value: RecordType | str | bool) -> RecordType:
    if isinstance(value, RecordType):
        return value
    if isinstance(value, bool):
        return RecordType.PRO if value else RecordType.NUB
    return RecordType(value)


RecordPbSortBy = Literal[
    "time",
    "points",
    "raw_rating_contribution",
    "created_at",
    "updated_at",
]


def seconds_to_time_ms(value: Decimal | float | int | str) -> int:
    decimal_value = Decimal(str(value))
    return int((decimal_value * 1000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def time_ms_to_seconds(time_ms: int) -> float:
    return round(time_ms / 1000, 3)


class MapCourseBase(SQLModel):
    map_id: int = Field(
        foreign_key="map.id",
        nullable=False,
    )
    stage: int = Field(default=0, ge=0)


class MapCourse(MapCourseBase, table=True):
    __tablename__ = "map_course"
    __table_args__ = (
        Index("ux_map_course_map_id_stage", "map_id", "stage", unique=True),
    )

    id: int | None = Field(default=None, primary_key=True)


class MapCourseTierBase(LegacyDatetimeNamesMixin):
    course_id: int = Field(
        foreign_key="map_course.id",
        primary_key=True,
    )
    mode: KZMode = Field(
        sa_column=Column(
            SqlEnum(KZMode, name="kz_mode"),
            ForeignKey("mode.name_short"),
            primary_key=True,
            nullable=False,
        )
    )
    tier: int = Field(default=0, ge=0, le=8)
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        validation_alias="created_on",
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        validation_alias="updated_on",
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
    updated_by_id: str | None = Field(
        default=None,
        max_length=32,
        sa_type=String(32),
    )

    def __init__(self, /, **data: object) -> None:
        super().__init__(**_normalize_record_payload(data))

    @model_validator(mode="before")
    @classmethod
    def _normalize_mode_input(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        return _normalize_record_payload(data)

    @property
    def mode_id(self) -> int:
        return kz_mode_to_legacy_mode_id(self.mode)


class MapCourseTier(MapCourseTierBase, table=True):
    __tablename__ = "map_course_tier"
    __table_args__ = (
        CheckConstraint(
            "tier >= 0 AND tier <= 8", name="ck_map_course_tier_range"
        ),
        Index("ix_map_course_tier_course_id", "course_id"),
        Index("ix_map_course_tier_mode", "mode"),
    )


class RecordBase(LegacyDatetimeNamesMixin):
    id: int | None = Field(default=None)
    steamid64: int = Field(
        foreign_key="player.steamid64",
        nullable=False,
        sa_type=BigInteger,
    )
    server_id: int = Field(
        foreign_key="server_globalapi.id",
        nullable=False,
    )
    mode: KZMode = Field(
        sa_column=Column(
            SqlEnum(KZMode, name="kz_mode"),
            ForeignKey("mode.name_short"),
            nullable=False,
        )
    )
    map_id: int = Field(
        foreign_key="map.id",
        nullable=False,
    )
    stage: int = Field(default=0, ge=0)
    time: Decimal = Field(
        sa_type=Numeric(12, 3),
    )
    teleports: int = Field(default=0, ge=0)
    points: int = Field(default=0, ge=0, le=1000)
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        validation_alias="created_on",
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        validation_alias="updated_on",
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
    updated_by: int = Field(
        default=0,
        sa_type=BigInteger,
    )
    replay_id: int | None = Field(default=None)
    is_valid: bool = True

    def __init__(self, /, **data: object) -> None:
        super().__init__(**_normalize_record_payload(data))

    @model_validator(mode="before")
    @classmethod
    def _normalize_mode_id_input(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        return _normalize_record_payload(data)

    @property
    def mode_id(self) -> int:
        return kz_mode_to_legacy_mode_id(self.mode)


class Record(RecordBase, table=True):
    __table_args__ = (
        CheckConstraint(
            "points >= 0 AND points <= 1000", name="ck_record_points_range"
        ),
        Index(
            "ux_record_id_not_null",
            "id",
            unique=True,
            postgresql_where=text("id IS NOT NULL"),
        ),
        Index(
            "ix_pb_map_pro",
            "map_id",
            "stage",
            "steamid64",
            "time",
            "mode",
            postgresql_where=text("is_valid = true AND teleports = 0"),
        ),
        Index(
            "ix_pb_map_nub",
            "map_id",
            "stage",
            "steamid64",
            "time",
            "mode",
            postgresql_where=text("is_valid = true AND teleports > 0"),
        ),
        Index(
            "ix_pb_map_ovr",
            "map_id",
            "stage",
            "steamid64",
            "time",
            "mode",
            postgresql_where=text("is_valid = true"),
        ),
        Index(
            "ix_record_valid_map_stage_mode_player_time",
            "map_id",
            "stage",
            "mode",
            "steamid64",
            "time",
            "id",
            "uuid",
            postgresql_where=text("is_valid = true"),
        ),
        Index(
            "ix_record_valid_pro_map_stage_mode_player_time",
            "map_id",
            "stage",
            "mode",
            "steamid64",
            "time",
            "id",
            "uuid",
            postgresql_where=text("is_valid = true AND teleports = 0"),
        ),
        Index(
            "ix_pb_player_pro",
            "steamid64",
            "map_id",
            "stage",
            "time",
            "mode",
            postgresql_where=text("is_valid = true AND teleports = 0"),
        ),
        Index(
            "ix_pb_player_nub",
            "steamid64",
            "map_id",
            "stage",
            "time",
            "mode",
            postgresql_where=text("is_valid = true AND teleports > 0"),
        ),
        Index(
            "ix_pb_player_ovr",
            "steamid64",
            "map_id",
            "stage",
            "time",
            "mode",
            postgresql_where=text("is_valid = true"),
        ),
        Index(
            "ix_record_valid_player_mode_map_stage_time",
            "steamid64",
            "mode",
            "map_id",
            "stage",
            "time",
            "id",
            "uuid",
            postgresql_where=text("is_valid = true"),
        ),
        Index(
            "ix_record_valid_pro_player_mode_map_stage_time",
            "steamid64",
            "mode",
            "map_id",
            "stage",
            "time",
            "id",
            "uuid",
            postgresql_where=text("is_valid = true AND teleports = 0"),
        ),
        Index(
            "ix_records_is_valid_server_id",
            "is_valid",
            "server_id",
        ),
        Index(
            "ix_records_steamid64_created_at",
            "steamid64",
            "created_at",
        ),
        Index(
            "ix_records_created_at_order",
            text("created_at DESC"),
            text("id DESC NULLS LAST"),
            text("uuid DESC"),
        ),
        Index(
            "ix_records_is_valid_created_at",
            "is_valid",
            text("created_at DESC"),
        ),
        Index(
            "ix_records_is_valid_updated_at",
            "is_valid",
            text("updated_at DESC"),
        ),
    )

    uuid: uuid.UUID = Field(default_factory=generate_uuid7, primary_key=True)


class RecordPbBase(LegacyDatetimeNamesMixin):
    scope: ModeScope = Field(
        sa_column=Column(
            SqlEnum(ModeScope, name="mode_scope"),
            primary_key=True,
            nullable=False,
        )
    )
    course_id: int = Field(foreign_key="map_course.id", primary_key=True)
    steamid64: int = Field(
        foreign_key="player.steamid64",
        sa_type=BigInteger,
        primary_key=True,
    )
    type: RecordType = Field(
        sa_column=Column(
            SqlEnum(RecordType, name="record_type"),
            primary_key=True,
            nullable=False,
        )
    )
    record_uuid: uuid.UUID = Field(foreign_key="record.uuid", nullable=False)
    time: Decimal = Field(
        sa_type=Numeric(12, 3),
    )
    points: int = Field(
        default=1,
        ge=1,
        le=1000,
        sa_column_kwargs={"server_default": text("1")},
    )
    raw_rating_contribution: int = Field(
        default=0,
        ge=0,
        sa_column_kwargs={"server_default": text("0")},
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        validation_alias="updated_on",
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )

    def __init__(self, /, **data: object) -> None:
        super().__init__(**_normalize_record_pb_payload(data))

    @model_validator(mode="before")
    @classmethod
    def _normalize_scope_input(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        return _normalize_record_pb_payload(data)

    @property
    def scope_id(self) -> int:
        return mode_scope_to_id(self.scope)


class RecordPb(RecordPbBase, table=True):
    __tablename__ = "record_pb"
    __table_args__ = (
        CheckConstraint(
            "points >= 1 AND points <= 1000", name="ck_record_pb_points_range"
        ),
        CheckConstraint(
            "raw_rating_contribution >= 0",
            name="ck_record_pb_raw_rating_contribution_non_negative",
        ),
        Index(
            "ix_record_pb_scope_course_type_record_uuid",
            "scope",
            "course_id",
            "type",
            "record_uuid",
        ),
        Index(
            "ix_record_pb_scope_course_type_time_record_uuid",
            "scope",
            "course_id",
            "type",
            "time",
            "record_uuid",
        ),
        Index(
            "ix_record_pb_player_scope_type_course_record_uuid",
            "steamid64",
            "scope",
            "type",
            "course_id",
            "record_uuid",
        ),
        Index(
            "ix_record_pb_record_uuid_scope_type",
            "record_uuid",
            "scope",
            "type",
        ),
        Index(
            "ix_record_pb_updated_at_desc",
            text("updated_at DESC"),
        ),
        Index(
            "ux_record_pb_wr_scope_course_type",
            "scope",
            "course_id",
            "type",
            unique=True,
            postgresql_where=text("points = 1000"),
        ),
    )


class RecordListQuery(SQLModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=10000)
    scope: ModeScope = ModeScope.OVR
    exclude_cheaters: bool = True
    id: list[int] | None = None
    steamid64: int | None = Field(default=None, sa_type=BigInteger)
    server_id: int | None = None
    mode_id: int | None = None
    map_id: int | None = None
    map_name: str | None = Field(default=None, max_length=255)
    stage: int | None = Field(default=None, ge=0)
    teleports: int | None = Field(default=None, ge=0)
    replay_id: int | None = None
    is_valid: bool | None = None
    created_since: datetime | None = None
    updated_since: datetime | None = None


class ReplayListQuery(SQLModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=10000)
    scope: ModeScope = ModeScope.OVR
    exclude_cheaters: bool = True
    steamid64: int | None = Field(default=None, sa_type=BigInteger)
    map_name: str | None = Field(default=None, max_length=255)
    mode: KZMode | None = None
    stage: int = Field(default=0, ge=0)
    teleports: int | None = Field(default=None, ge=0)


class RecordPatch(SQLModel):
    model_config = {"extra": "forbid"}

    is_valid: bool


class RecordBulkDeleteCourse(SQLModel):
    model_config = {"extra": "forbid"}

    steamid64: str
    map_id: int
    stage: int = Field(ge=0)


class RecordBulkDeleteResult(SQLModel):
    data: list[RecordPublic]
    count: int


class RecordPbBucketRebuildResult(SQLModel):
    course_id: int
    scope: ModeScope
    type: RecordType
    updated_count: int


class RecordPublic(SQLModel):
    uuid: uuid.UUID
    id: int | None = None
    player: PlayerRefPublic
    steam_id: str | None = None
    server_id: int
    server_name: str
    server_group: ServerGroupSummary | None = None
    map_id: int
    map_name: str
    workshop_id: int | None = None
    map_tier: int
    mode_id: int
    mode: str
    stage: int
    tickrate: int = 128
    time: float
    teleports: int
    points: int
    raw_rating_contribution: int = 0
    created_on: datetime
    updated_on: datetime
    updated_by: str
    replay_id: int | None = None
    is_replay_available: bool
    is_valid: bool


class RecordsPublic(SQLModel):
    data: list[RecordPublic]
    count: int


class RecordRankPublic(SQLModel):
    record_uuid: uuid.UUID
    rank: int | None = None
    total_count: int | None = None


class RecordRanksPublic(SQLModel):
    data: list[RecordRankPublic]
    count: int


class RecordRunHistoryEntryPublic(SQLModel):
    uuid: uuid.UUID
    id: int | None = None
    server_id: int
    server_name: str
    mode_id: int
    mode: str
    time: float
    teleports: int
    wr_gap: float | None = None
    is_pb: bool
    created_on: datetime
    is_replay_available: bool


class RecordRunHistoryPublic(SQLModel):
    data: list[RecordRunHistoryEntryPublic]
    count: int
    wr_time: float | None = None


class MapPbLeaderboardPublic(SQLModel):
    data: list[RecordPublic]
    count: int
    unique_nub_finishes: int
    unique_pro_finishes: int
    current_user_rank: int | None = None
    current_user_steamid64: str | None = None


class MapWrPublic(SQLModel):
    record_uuid: uuid.UUID
    map_id: int
    scope: ModeScope
    type: RecordType
    mode_id: int
    player: PlayerRefPublic
    time: float
    updated_at: datetime


class RecentRecordMapPublic(SQLModel):
    id: int
    name: str
    tier: int


class RecentRecordServerPublic(SQLModel):
    id: int
    name: str
    group: ServerGroupSummary | None = None


class RecentRecordModePublic(SQLModel):
    id: int
    name: str


class RecentRecordPublic(SQLModel):
    uuid: uuid.UUID
    id: int | None = None
    player: PlayerRefPublic
    map: RecentRecordMapPublic
    server: RecentRecordServerPublic
    mode: RecentRecordModePublic
    stage: int
    teleports: int
    time: float
    points: int
    created_on: datetime
    updated_on: datetime
    is_replay_available: bool


class RecentRecordsPublic(SQLModel):
    data: list[RecentRecordPublic]
    count: int


class RecentRecordListQuery(SQLModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=100000)
    scope: ModeScope = ModeScope.OVR
    mode: KZMode | None = None
    map_id: int | None = Field(default=None, ge=1)
    stage: int | None = Field(default=None, ge=0)
    is_bonus: bool | None = None
    tier: int | None = Field(default=None, ge=0, le=8)
    points_more_or_equal_than: int | None = Field(default=None, ge=0, le=1000)
    points_less_or_equal_than: int | None = Field(default=None, ge=0, le=1000)
    type: RecordType | None = None
    is_pro_only: bool | None = None


class RecentRecordSnapshotEvent(SQLModel):
    type: Literal["record.snapshot"] = "record.snapshot"
    records: list[RecentRecordPublic]


class RecentRecordUpsertEvent(SQLModel):
    type: Literal["record.upserted"] = "record.upserted"
    record: RecentRecordPublic


class RecordCompatPublicV0(SQLModel):
    id: int
    steamid64: str
    player_name: str
    steam_id: str | None = None
    server_id: int
    server_name: str
    map_id: int
    map_name: str
    mode: str
    stage: int
    tickrate: int = 128
    time: float
    teleports: int
    points: int
    created_on: datetime
    updated_on: datetime
    updated_by: int
    record_filter_id: int = 0
    replay_id: int | None = None
    server: ServerGlobalapiCompatPublicV0 | None = None


class TopRecordCompatPublicV0(SQLModel):
    id: int
    steamid64: str
    player_name: str
    steam_id: str | None = None
    server_id: int
    map_id: int
    stage: int
    mode: str
    tickrate: int = 128
    time: float
    teleports: int
    created_on: datetime
    updated_on: datetime
    updated_by: int
    record_filter_id: int = 0
    server_name: str
    map_name: str
    points: int
    replay_id: int = 0


class RecentRecordCompatPublicV0(RecordCompatPublicV0):
    place: int
    place_overall: int
    top_100: bool
    top_100_overall: bool


class WorldRecordCountCompatPublicV0(SQLModel):
    steamid64: int
    player_name: str
    steam_id: str | None = None
    world_records: int


class AdminCourseTierPublic(SQLModel):
    course_id: int
    map_id: int
    stage: int
    mode: KZMode
    tier: int
    created_on: datetime | None = None
    updated_on: datetime | None = None
    updated_by_id: str | None = None


class AdminMapCourseTierStagePublic(SQLModel):
    stage: int
    course_id: int
    course_tiers: list[AdminCourseTierPublic]


class AdminMapCourseTiersPublic(SQLModel):
    map_id: int
    stages: list[AdminMapCourseTierStagePublic]


class AdminCourseTierUpdate(SQLModel):
    model_config = {"extra": "forbid"}

    tier: int = Field(ge=0, le=8)
