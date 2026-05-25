import uuid
from datetime import datetime

from pydantic import field_validator
from sqlalchemy import BigInteger, Column, DateTime, Index
from sqlmodel import Field, SQLModel

from .player import PlayerRefPublic
from .utils import generate_uuid7, get_datetime_utc

MAX_PLAYER_COMMENT_LENGTH = 500


def normalize_player_comment_text(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("comment text must not be blank")
    if len(normalized) > MAX_PLAYER_COMMENT_LENGTH:
        raise ValueError(
            f"comment text must be at most {MAX_PLAYER_COMMENT_LENGTH} characters"
        )
    return normalized


class PlayerCommentCreate(SQLModel):
    text: str = Field(min_length=1, max_length=MAX_PLAYER_COMMENT_LENGTH)

    @field_validator("text", mode="after")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        return normalize_player_comment_text(value)


class PlayerCommentPublic(SQLModel):
    id: uuid.UUID
    text: str
    created_at: datetime
    updated_at: datetime
    author: PlayerRefPublic


class PlayerCommentsPublic(SQLModel):
    data: list[PlayerCommentPublic]
    count: int


class PlayerCommentListQuery(SQLModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


class PlayerComment(SQLModel, table=True):
    __tablename__ = "player_comment"
    __table_args__ = (
        Index(
            "ix_player_comment_target_created_at_id",
            "target_steamid64",
            "created_at",
            "id",
        ),
        Index(
            "ix_player_comment_author_created_at_id",
            "author_steamid64",
            "created_at",
            "id",
        ),
    )

    id: uuid.UUID = Field(default_factory=generate_uuid7, primary_key=True)
    author_steamid64: int = Field(
        foreign_key="player.steamid64",
        sa_type=BigInteger,
        ondelete="CASCADE",
    )
    target_steamid64: int = Field(
        foreign_key="player.steamid64",
        sa_type=BigInteger,
        ondelete="CASCADE",
    )
    text: str = Field(max_length=MAX_PLAYER_COMMENT_LENGTH)
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    @field_validator("text", mode="after")
    @classmethod
    def _normalize_text(cls, value: str) -> str:
        return normalize_player_comment_text(value)
