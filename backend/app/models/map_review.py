import uuid
from datetime import datetime
from typing import Literal
from typing import Any

from pydantic import field_validator
from sqlalchemy import BigInteger, Column, DateTime, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from .map import MapRefPublic
from .player import PlayerRefPublic
from .utils import generate_uuid7, get_datetime_utc


def _normalize_comment_text(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > 1000:
        raise ValueError("comment text must be at most 1000 characters")
    return normalized


class MapReviewCommentInput(SQLModel):
    text: str | None = Field(default=None, max_length=1000)

    @field_validator("text", mode="after")
    @classmethod
    def _validate_text(cls, value: str | None) -> str | None:
        return _normalize_comment_text(value)


class MapReviewContentInput(SQLModel):
    overall: int = Field(ge=1, le=5)
    gameplay: int | None = Field(default=None, ge=1, le=5)
    visuals: int | None = Field(default=None, ge=1, le=5)
    comment: MapReviewCommentInput | None = None


class MapReviewUpsert(SQLModel):
    map_id: int
    steamid64: int | None = Field(default=None, sa_type=BigInteger)
    content: MapReviewContentInput


class MapReviewCommentPublic(SQLModel):
    text: str
    language: str
    created_at: datetime
    updated_at: datetime


class MapReviewContentPublic(SQLModel):
    overall: int
    gameplay: int | None = None
    visuals: int | None = None
    comment: MapReviewCommentPublic | None = None


class MapReview(SQLModel, table=True):
    __tablename__ = "map_review"
    __table_args__ = (
        UniqueConstraint(
            "steamid64",
            "map_id",
            "server_group_id",
            name="uq_map_review_context",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_map_review_map_id_steamid64_updated_at", "map_id", "steamid64", "updated_at"),
        Index("ix_map_review_steamid64_map_id_updated_at", "steamid64", "map_id", "updated_at"),
        Index("ix_map_review_server_group_id_updated_at", "server_group_id", "updated_at"),
    )

    id: uuid.UUID = Field(default_factory=generate_uuid7, primary_key=True)
    steamid64: int = Field(
        foreign_key="player.steamid64",
        sa_type=BigInteger,
        ondelete="CASCADE",
    )
    map_id: int = Field(
        foreign_key="map.id",
        ondelete="CASCADE",
    )
    server_group_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="server_group.id",
        ondelete="CASCADE",
    )
    content: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False),
    )
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class MapReviewPublic(SQLModel):
    steamid64: str
    map_id: int
    server_group_id: uuid.UUID | None = None
    content: MapReviewContentPublic
    created_at: datetime
    updated_at: datetime
    player: PlayerRefPublic
    map: MapRefPublic


class MapReviewsPublic(SQLModel):
    data: list[MapReviewPublic]
    count: int


MapReviewSource = Literal["latest", "website"]


class MapReviewListQuery(SQLModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=1000)
    map_id: int | None = None
    map_name: str | None = Field(default=None, max_length=255)
    steamid64: int | None = Field(default=None, sa_type=BigInteger)
    with_comments_only: bool = False
    language: str | None = Field(default=None, min_length=1, max_length=16)
    source: MapReviewSource = "latest"
