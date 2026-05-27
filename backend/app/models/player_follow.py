from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, ForeignKey, Index
from sqlmodel import Field, SQLModel

from .utils import get_datetime_utc


class PlayerFollow(SQLModel, table=True):
    __tablename__ = "player_follow"
    __table_args__ = (
        CheckConstraint(
            "follower_steamid64 != followed_steamid64",
            name="ck_player_follow_not_self",
        ),
        Index(
            "ix_player_follow_followed_created_at",
            "followed_steamid64",
            "created_at",
        ),
        Index(
            "ix_player_follow_follower_created_at",
            "follower_steamid64",
            "created_at",
        ),
    )

    follower_steamid64: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("player.steamid64", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    followed_steamid64: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("player.steamid64", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class PlayerFollowSummaryPublic(SQLModel):
    follower_count: int = 0
    following_count: int = 0
    viewer_is_following: bool | None = None
    viewer_is_self: bool = False


class PlayerFollowListQuery(SQLModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)
