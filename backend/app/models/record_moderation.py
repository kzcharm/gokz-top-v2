import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Column, DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from .utils import generate_uuid7, get_datetime_utc


class RecordModerationActionType(StrEnum):
    SINGLE_SOFT_DELETE = "single_soft_delete"
    SINGLE_REENABLE = "single_reenable"
    BULK_SOFT_DELETE_COURSE = "bulk_soft_delete_course"


class RecordModerationAction(SQLModel, table=True):
    __tablename__ = "record_moderation_action"
    __table_args__ = (
        Index(
            "ix_record_moderation_action_actor_created_at",
            "actor_steamid64",
            "created_at",
        ),
        Index(
            "ix_record_moderation_action_target_player_created_at",
            "target_player_steamid64",
            "created_at",
        ),
        Index(
            "ix_record_moderation_action_target_map_stage_created_at",
            "target_map_id",
            "target_stage",
            "created_at",
        ),
    )

    id: uuid.UUID = Field(default_factory=generate_uuid7, primary_key=True)
    actor_steamid64: int = Field(
        foreign_key="player.steamid64",
        nullable=False,
        sa_type=BigInteger,
    )
    action_type: RecordModerationActionType = Field(
        sa_column=Column(
            String(32),
            nullable=False,
        )
    )
    target_record_uuid: uuid.UUID | None = Field(
        default=None,
        foreign_key="record.uuid",
        nullable=True,
    )
    target_player_steamid64: int | None = Field(
        default=None,
        foreign_key="player.steamid64",
        nullable=True,
        sa_type=BigInteger,
    )
    target_map_id: int | None = Field(
        default=None,
        foreign_key="map.id",
        nullable=True,
    )
    target_stage: int | None = Field(default=None, ge=0)
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )


class RecordModerationActionRecord(SQLModel, table=True):
    __tablename__ = "record_moderation_action_record"
    __table_args__ = (
        Index(
            "ix_record_moderation_action_record_action_id",
            "action_id",
        ),
        Index(
            "ix_record_moderation_action_record_record_uuid",
            "record_uuid",
        ),
    )

    id: uuid.UUID = Field(default_factory=generate_uuid7, primary_key=True)
    action_id: uuid.UUID = Field(
        foreign_key="record_moderation_action.id",
        nullable=False,
    )
    record_uuid: uuid.UUID = Field(
        foreign_key="record.uuid",
        nullable=False,
    )
    record_id: int | None = Field(default=None)
    player_steamid64: int = Field(
        foreign_key="player.steamid64",
        nullable=False,
        sa_type=BigInteger,
    )
    map_id: int = Field(
        foreign_key="map.id",
        nullable=False,
    )
    stage: int = Field(ge=0)
    before_snapshot: dict[str, object] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )
    after_snapshot: dict[str, object] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[arg-type]
    )
