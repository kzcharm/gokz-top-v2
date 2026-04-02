import uuid
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import IntEnum, StrEnum
from typing import Literal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    Numeric,
    SmallInteger,
    text,
)
from sqlmodel import Field, SQLModel

from .server_globalapi import ServerGlobalapiCompatPublicV0
from .utils import generate_uuid7, get_datetime_utc


class TeleportsType(StrEnum):
    PRO = "PRO"
    NUB = "NUB"
    OVR = "OVR"


class RecordScope(StrEnum):
    OVR = "OVR"
    KZT = "KZT"
    SKZ = "SKZ"
    VNL = "VNL"


class RecordScopeId(IntEnum):
    OVR = 0
    KZT = 1
    SKZ = 2
    VNL = 3


SCOPE_ID_BY_SCOPE: dict[RecordScope, int] = {
    RecordScope.OVR: RecordScopeId.OVR,
    RecordScope.KZT: RecordScopeId.KZT,
    RecordScope.SKZ: RecordScopeId.SKZ,
    RecordScope.VNL: RecordScopeId.VNL,
}

SCOPE_MODE_IDS: dict[int, tuple[int, ...]] = {
    RecordScopeId.OVR: (200, 201, 202, 203),
    RecordScopeId.KZT: (200, 203),
    RecordScopeId.SKZ: (201,),
    RecordScopeId.VNL: (202,),
}


def scope_to_id(scope: RecordScope) -> int:
    return int(SCOPE_ID_BY_SCOPE[scope])


def scope_mode_ids(scope_id: int) -> tuple[int, ...]:
    return SCOPE_MODE_IDS[scope_id]


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


class RecordBase(SQLModel):
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
    mode_id: int = Field(
        foreign_key="mode.id",
        nullable=False,
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
    created_on: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
    updated_on: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
    updated_by: int = Field(
        default=0,
        sa_type=BigInteger,
    )
    replay_id: int | None = Field(default=None)
    is_valid: bool = True


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
            "mode_id",
            postgresql_where=text("is_valid = true AND teleports = 0"),
        ),
        Index(
            "ix_pb_map_nub",
            "map_id",
            "stage",
            "steamid64",
            "time",
            "mode_id",
            postgresql_where=text("is_valid = true AND teleports > 0"),
        ),
        Index(
            "ix_pb_map_ovr",
            "map_id",
            "stage",
            "steamid64",
            "time",
            "mode_id",
            postgresql_where=text("is_valid = true"),
        ),
        Index(
            "ix_record_valid_map_stage_mode_player_time",
            "map_id",
            "stage",
            "mode_id",
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
            "mode_id",
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
            "mode_id",
            postgresql_where=text("is_valid = true AND teleports = 0"),
        ),
        Index(
            "ix_pb_player_nub",
            "steamid64",
            "map_id",
            "stage",
            "time",
            "mode_id",
            postgresql_where=text("is_valid = true AND teleports > 0"),
        ),
        Index(
            "ix_pb_player_ovr",
            "steamid64",
            "map_id",
            "stage",
            "time",
            "mode_id",
            postgresql_where=text("is_valid = true"),
        ),
        Index(
            "ix_record_valid_player_mode_map_stage_time",
            "steamid64",
            "mode_id",
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
            "mode_id",
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
            "ix_records_created_on_order",
            text("created_on DESC"),
            text("id DESC NULLS LAST"),
            text("uuid DESC"),
        ),
        Index(
            "ix_records_is_valid_created_on",
            "is_valid",
            text("created_on DESC"),
        ),
        Index(
            "ix_records_is_valid_updated_on",
            "is_valid",
            text("updated_on DESC"),
        ),
    )

    uuid: uuid.UUID = Field(default_factory=generate_uuid7, primary_key=True)


class RecordPbBase(SQLModel):
    scope: int = Field(sa_type=SmallInteger, primary_key=True)
    course_id: int = Field(foreign_key="map_course.id", primary_key=True)
    steamid64: int = Field(
        foreign_key="player.steamid64",
        sa_type=BigInteger,
        primary_key=True,
    )
    is_pro_only: bool = Field(primary_key=True)
    record_uuid: uuid.UUID = Field(foreign_key="record.uuid", nullable=False)
    time_ms: int = Field(sa_type=BigInteger)
    points: int = Field(
        default=1,
        ge=1,
        le=1000,
        sa_column_kwargs={"server_default": text("1")},
    )
    updated_on: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )


class RecordPb(RecordPbBase, table=True):
    __tablename__ = "record_pb"
    __table_args__ = (
        CheckConstraint(
            "points >= 1 AND points <= 1000", name="ck_record_pb_points_range"
        ),
        Index(
            "ix_record_pb_scope_course_pro_time_uuid",
            "scope",
            "course_id",
            "is_pro_only",
            "time_ms",
            "record_uuid",
        ),
        Index(
            "ix_record_pb_player_scope_pro_course_time",
            "steamid64",
            "scope",
            "is_pro_only",
            "course_id",
            "time_ms",
        ),
        Index(
            "ix_record_pb_record_uuid_scope_pro",
            "record_uuid",
            "scope",
            "is_pro_only",
        ),
    )


class RecordListQuery(SQLModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=10000)
    scope: RecordScope = RecordScope.OVR
    id: list[int] | None = None
    steamid64: int | None = Field(default=None, sa_type=BigInteger)
    server_id: int | None = None
    mode_id: int | None = None
    map_id: int | None = None
    stage: int | None = Field(default=None, ge=0)
    teleports: int | None = Field(default=None, ge=0)
    replay_id: int | None = None
    is_valid: bool | None = None
    created_since: datetime | None = None
    updated_since: datetime | None = None


class RecordPatch(SQLModel):
    model_config = {"extra": "forbid"}

    is_valid: bool


class RecordPublic(SQLModel):
    uuid: uuid.UUID
    id: int | None = None
    steamid64: str
    player_name: str
    player_avatar_hash: str | None = None
    steam_id: str | None = None
    server_id: int
    server_name: str
    map_id: int
    map_name: str
    mode_id: int
    mode: str
    stage: int
    tickrate: int = 128
    time: float
    teleports: int
    points: int
    created_on: datetime
    updated_on: datetime
    updated_by: str
    replay_id: int | None = None
    is_valid: bool


class RecordsPublic(SQLModel):
    data: list[RecordPublic]
    count: int


class RecentRecordPlayerPublic(SQLModel):
    steamid64: str
    name: str
    alias: str | None = None
    avatar_hash: str | None = None
    country: str | None = None


class RecentRecordMapPublic(SQLModel):
    id: int
    name: str
    tier: int


class RecentRecordServerPublic(SQLModel):
    id: int
    name: str


class RecentRecordModePublic(SQLModel):
    id: int
    name: str


class RecentRecordPublic(SQLModel):
    uuid: uuid.UUID
    id: int | None = None
    player: RecentRecordPlayerPublic
    map: RecentRecordMapPublic
    server: RecentRecordServerPublic
    mode: RecentRecordModePublic
    stage: int
    teleports: int
    time: float
    points: int
    created_on: datetime
    updated_on: datetime


class RecentRecordsPublic(SQLModel):
    data: list[RecentRecordPublic]
    count: int


class RecentRecordListQuery(SQLModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=10000)
    scope: RecordScope = RecordScope.OVR
    points_more_or_equal_than: int | None = Field(default=None, ge=0, le=1000)
    is_pro_only: bool | None = None


class RecentRecordSnapshotEvent(SQLModel):
    type: Literal["record.snapshot"] = "record.snapshot"
    records: list[RecentRecordPublic]


class RecentRecordUpsertEvent(SQLModel):
    type: Literal["record.upserted"] = "record.upserted"
    record: RecentRecordPublic


class RecordCompatPublicV0(SQLModel):
    id: int
    steamid64: int
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
