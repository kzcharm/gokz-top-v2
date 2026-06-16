import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Text, Uuid
from sqlmodel import Field, SQLModel

from .utils import generate_uuid7, get_datetime_utc

MAX_PLAYER_REPORT_DESCRIPTION_LENGTH = 1000


def normalize_player_report_description(text: str) -> str:
    return text.strip()


class PlayerReportCreate(SQLModel):
    target_steamid64: str
    description: str = Field(max_length=MAX_PLAYER_REPORT_DESCRIPTION_LENGTH)
    record_uuid: uuid.UUID | None = None


class PlayerReportPublic(SQLModel):
    id: uuid.UUID
    reporter_steamid64: str
    target_steamid64: str
    record_uuid: uuid.UUID | None = None
    description: str
    created_at: datetime


class PlayerReport(SQLModel, table=True):
    __tablename__ = "player_report"
    __table_args__ = (
        Index(
            "ix_player_report_target_created_at",
            "target_steamid64",
            "created_at",
        ),
        Index(
            "ix_player_report_reporter_created_at",
            "reporter_steamid64",
            "created_at",
        ),
        Index(
            "ix_player_report_record_uuid",
            "record_uuid",
        ),
    )

    id: uuid.UUID = Field(default_factory=generate_uuid7, primary_key=True)
    reporter_steamid64: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("player.steamid64", ondelete="CASCADE"),
            nullable=False,
        )
    )
    target_steamid64: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("player.steamid64", ondelete="CASCADE"),
            nullable=False,
        )
    )
    record_uuid: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(
            Uuid,
            ForeignKey("record.uuid", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    description: str = Field(
        sa_column=Column(Text, nullable=False),
        max_length=MAX_PLAYER_REPORT_DESCRIPTION_LENGTH,
    )
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
