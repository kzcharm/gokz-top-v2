import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlmodel import Field, SQLModel

from .player import PlayerRefPublic
from .utils import generate_uuid7, get_datetime_utc


class ReactionTargetType(StrEnum):
    MEDIA_POST = "media_post"
    RECENT_WR = "recent_wr"
    MAP_REVIEW_COMMENT = "map_review_comment"
    POLL = "poll"
    RELEASE = "release"


class ContentReaction(SQLModel, table=True):
    __tablename__ = "content_reaction"
    __table_args__ = (
        CheckConstraint(
            "content_type IN ('media_post', 'recent_wr', 'map_review_comment', 'poll', 'release')",
            name="ck_content_reaction_content_type",
        ),
        UniqueConstraint(
            "user_steamid64",
            "emoji_key",
            "content_type",
            "content_id",
            name="uq_content_reaction_user_emoji_target",
        ),
        Index(
            "ix_content_reaction_target",
            "content_type",
            "content_id",
            "emoji_key",
        ),
    )

    id: uuid.UUID = Field(default_factory=generate_uuid7, primary_key=True)
    user_steamid64: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("user.steamid64", ondelete="CASCADE"),
            nullable=False,
        )
    )
    emoji_key: str = Field(max_length=128)
    content_type: ReactionTargetType = Field(
        sa_column=Column(String(32), nullable=False)
    )
    content_id: str = Field(sa_column=Column(String(64), nullable=False))
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class ReactionEmojiPublic(SQLModel):
    key: str
    name: str
    value: str | None = None
    image_url: str | None = None


class ReactionCreate(SQLModel):
    emoji_key: str = Field(min_length=1, max_length=128)


class ReactionGroupPublic(SQLModel):
    emoji: ReactionEmojiPublic
    count: int
    reacted_by_me: bool = False
    reaction_id: uuid.UUID | None = None


class ReactionSummaryPublic(SQLModel):
    groups: list[ReactionGroupPublic] = Field(default_factory=list)


class ReactionPlayerPublic(PlayerRefPublic):
    avatar_hash: str | None = None


class ReactionUserPublic(SQLModel):
    player: ReactionPlayerPublic
    created_at: datetime


class ReactionUsersPublic(SQLModel):
    data: list[ReactionUserPublic]
    count: int
