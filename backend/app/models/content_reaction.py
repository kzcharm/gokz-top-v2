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
            "num_nonnulls(media_post_id, record_uuid, map_review_id, poll_id, github_release_id) = 1",
            name="ck_content_reaction_exactly_one_target",
        ),
        UniqueConstraint(
            "user_steamid64",
            "emoji_key",
            "media_post_id",
            "record_uuid",
            "map_review_id",
            "poll_id",
            "github_release_id",
            name="uq_content_reaction_user_emoji_target",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_content_reaction_media_post", "media_post_id", "emoji_key"),
        Index("ix_content_reaction_record", "record_uuid", "emoji_key"),
        Index("ix_content_reaction_map_review", "map_review_id", "emoji_key"),
        Index("ix_content_reaction_poll", "poll_id", "emoji_key"),
        Index("ix_content_reaction_release", "github_release_id", "emoji_key"),
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
    media_post_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="media_post.id",
        ondelete="CASCADE",
    )
    record_uuid: uuid.UUID | None = Field(
        default=None,
        foreign_key="record.uuid",
        ondelete="CASCADE",
    )
    map_review_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="map_review.id",
        ondelete="CASCADE",
    )
    poll_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="poll.id",
        ondelete="CASCADE",
    )
    github_release_id: int | None = Field(
        default=None,
        sa_column=Column(
            BigInteger,
            ForeignKey("github_release.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
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
