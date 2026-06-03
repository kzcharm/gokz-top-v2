import uuid
from datetime import datetime
from enum import StrEnum
from typing import Literal

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy import Enum as SqlEnum
from sqlmodel import Field, SQLModel

from .mode_scope import ModeScope
from .player import PlayerRefPublic
from .record import RecordType
from .utils import generate_uuid7, get_datetime_utc


class PlayerNotificationType(StrEnum):
    PROFILE_LIKE = "profile_like"
    PROFILE_COMMENT = "profile_comment"
    PLAYER_FOLLOW = "player_follow"
    WR_BEATEN = "wr_beaten"


class PlayerNotificationListQuery(SQLModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)
    unread_only: bool = False


class PlayerNotificationUnreadCountPublic(SQLModel):
    unread_count: int = Field(ge=0)


class PlayerNotificationPublic(SQLModel):
    id: uuid.UUID
    type: PlayerNotificationType
    created_at: datetime
    read_at: datetime | None = None
    actor: PlayerRefPublic | None = None
    target_url: str
    target_player_steamid64: str | None = None
    comment_id: uuid.UUID | None = None
    comment_preview: str | None = None
    map_id: int | None = None
    map_name: str | None = None
    scope: ModeScope | None = None
    record_type: RecordType | None = None
    previous_record_uuid: uuid.UUID | None = None
    new_record_uuid: uuid.UUID | None = None
    new_record_time: float | None = None


class PlayerNotificationsPublic(SQLModel):
    data: list[PlayerNotificationPublic]
    count: int


class PlayerNotification(SQLModel, table=True):
    __tablename__ = "player_notification"
    __table_args__ = (
        Index(
            "ux_player_notification_source_key",
            "source_key",
            unique=True,
        ),
        Index(
            "ix_player_notification_recipient_created_at",
            "recipient_steamid64",
            "created_at",
            "id",
        ),
        Index(
            "ix_player_notification_recipient_read_at_created_at",
            "recipient_steamid64",
            "read_at",
            "created_at",
        ),
    )

    id: uuid.UUID = Field(default_factory=generate_uuid7, primary_key=True)
    recipient_steamid64: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("player.steamid64", ondelete="CASCADE"),
            nullable=False,
        )
    )
    actor_steamid64: int | None = Field(
        default=None,
        sa_column=Column(
            BigInteger,
            ForeignKey("player.steamid64", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    type: PlayerNotificationType = Field(
        sa_column=Column(
            SqlEnum(
                PlayerNotificationType,
                name="player_notification_type",
                values_callable=lambda enum_class: [
                    member.value for member in enum_class
                ],
            ),
            nullable=False,
        )
    )
    source_key: str = Field(sa_column=Column(String(255), nullable=False))
    target_url: str = Field(sa_column=Column(Text, nullable=False))
    target_player_steamid64: int | None = Field(default=None, sa_type=BigInteger)
    comment_id: uuid.UUID | None = None
    comment_preview: str | None = Field(default=None, max_length=140)
    map_id: int | None = Field(default=None, foreign_key="map.id")
    map_name: str | None = Field(default=None, max_length=255)
    scope: ModeScope | None = Field(
        default=None,
        sa_column=Column(
            SqlEnum(ModeScope, name="mode_scope"),
            nullable=True,
        ),
    )
    record_type: RecordType | None = Field(
        default=None,
        sa_column=Column(
            SqlEnum(RecordType, name="record_type"),
            nullable=True,
        ),
    )
    previous_record_uuid: uuid.UUID | None = None
    new_record_uuid: uuid.UUID | None = None
    new_record_time: float | None = None
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    read_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )


PlayerNotificationPatchResult = Literal["updated", "not_found", "not_owner"]
