import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, Numeric, text
from sqlmodel import Field, SQLModel

from .server_globalapi import ServerGlobalapiCompatPublicV0
from .utils import generate_uuid7, get_datetime_utc


class TeleportsType(StrEnum):
    PRO = "PRO"
    NUB = "NUB"
    OVR = "OVR"


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
            "ix_records_is_valid_server_id",
            "is_valid",
            "server_id",
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


class RecordListQuery(SQLModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=10000)
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
