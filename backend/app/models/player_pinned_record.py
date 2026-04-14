import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index
from sqlalchemy import Enum as SqlEnum
from sqlmodel import Field, SQLModel

from .record import ModeScope, RecordPublic, RecordType
from .utils import generate_uuid7, get_datetime_utc


class PlayerPinnedRecord(SQLModel, table=True):
    __tablename__ = "player_pinned_record"
    __table_args__ = (
        Index(
            "ix_player_pinned_record_player_scope_created_at",
            "player_steamid64",
            "scope",
            "created_at",
        ),
        Index(
            "ux_player_pinned_record_player_map_scope_type",
            "player_steamid64",
            "map_id",
            "scope",
            "type",
            unique=True,
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
    map_id: int = Field(
        sa_column=Column(
            ForeignKey("map.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    scope: ModeScope = Field(
        sa_column=Column(
            SqlEnum(ModeScope, name="mode_scope"),
            nullable=False,
        )
    )
    type: RecordType = Field(
        sa_column=Column(
            SqlEnum(RecordType, name="record_type"),
            nullable=False,
        )
    )
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )


class PlayerPinnedRecordUpsert(SQLModel):
    map_id: int
    scope: ModeScope
    type: RecordType


class PlayerPinnedRecordPublic(SQLModel):
    id: uuid.UUID
    player_steamid64: str
    map_id: int
    scope: ModeScope
    type: RecordType
    created_at: datetime
    updated_at: datetime
    record: RecordPublic


class PlayerPinnedRecordsPublic(SQLModel):
    data: list[PlayerPinnedRecordPublic]
    count: int
