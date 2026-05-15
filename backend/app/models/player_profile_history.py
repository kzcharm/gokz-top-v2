import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, ForeignKey, Index
from sqlmodel import Field, SQLModel

from .utils import generate_uuid7


class PlayerProfileHistory(SQLModel, table=True):
    __tablename__ = "player_profile_history"
    __table_args__ = (
        CheckConstraint(
            "name IS NOT NULL OR avatar_hash IS NOT NULL",
            name="ck_player_profile_history_name_or_avatar_present",
        ),
        Index(
            "ix_player_profile_history_player_steamid64_changed_at",
            "player_steamid64",
            "changed_at",
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
    name: str | None = Field(default=None, max_length=255)
    avatar_hash: str | None = Field(default=None, max_length=255)
    changed_at: datetime = Field(
        sa_type=DateTime(timezone=True),  # type: ignore
        nullable=False,
    )


class PlayerProfileHistoryListQuery(SQLModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=100)


class PlayerProfileHistoryEntryPublic(SQLModel):
    id: uuid.UUID
    name: str | None = None
    avatar_hash: str | None = None
    changed_at: datetime


class PlayerProfileHistoryPublic(SQLModel):
    data: list[PlayerProfileHistoryEntryPublic]
    count: int
