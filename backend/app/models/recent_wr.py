import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Column, DateTime, ForeignKey, Index, Numeric, text
from sqlalchemy import Enum as SqlEnum
from sqlmodel import Field, SQLModel

from .mode_scope import ModeScope
from .record import RecentRecordPublic, RecordType


class RecentWrEventCache(SQLModel, table=True):
    __tablename__ = "recent_wr_events"
    __table_args__ = (
        Index(
            "ix_cache_recent_wr_events_scope_created_at",
            "scope",
            text("event_created_at DESC"),
            text("record_uuid DESC"),
        ),
        Index(
            "ix_cache_recent_wr_events_map_scope_type",
            "map_id",
            "scope",
            "type",
        ),
        {"schema": "cache"},
    )

    record_uuid: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("record.uuid", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        )
    )
    scope: ModeScope = Field(
        sa_column=Column(
            SqlEnum(ModeScope, name="mode_scope"),
            primary_key=True,
            nullable=False,
        )
    )
    type: RecordType = Field(
        sa_column=Column(
            SqlEnum(RecordType, name="record_type"),
            primary_key=True,
            nullable=False,
        )
    )
    map_id: int = Field(
        sa_column=Column(
            ForeignKey("map.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    previous_record_uuid: uuid.UUID | None = None
    previous_time: Decimal | None = Field(
        default=None,
        sa_column=Column(Numeric(12, 3), nullable=True),
    )
    event_created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )


class RecentWrAchievementPublic(SQLModel):
    type: RecordType
    previous_record_uuid: uuid.UUID | None = None
    previous_player_name: str | None = None
    previous_time: float | None = None
    improvement_seconds: float | None = None


class RecentWrPublic(SQLModel):
    record: RecentRecordPublic
    achievements: list[RecentWrAchievementPublic]


class RecentWrsPublic(SQLModel):
    data: list[RecentWrPublic]
    count: int


class RecentWrListQuery(SQLModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)
    scope: ModeScope = ModeScope.OVR
    map_id: int | None = Field(default=None, ge=1)
    tier: int | None = Field(default=None, ge=0, le=8)
    type: RecordType | None = None


class RecentWrSnapshotEvent(SQLModel):
    type: str = "recent_wrs.snapshot"
    data: list[RecentWrPublic]
    count: int
