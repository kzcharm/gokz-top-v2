from typing import Literal

from sqlmodel import Field, SQLModel

from .player import PlayerRefPublic
from .video_platform_followers import VideoPlatformFollowerPublic

CommunityLeaderboardSortBy = Literal[
    "views_count",
    "unique_visitors",
    "likes",
    "unique_likers",
    "platform_followers",
]


class CommunityLeaderboardEntryPublic(SQLModel):
    rank: int
    player: PlayerRefPublic
    views_count: int
    unique_visitors: int
    likes: int
    unique_likers: int
    video_platform_followers: VideoPlatformFollowerPublic | None = None


class CommunityLeaderboardsPublic(SQLModel):
    data: list[CommunityLeaderboardEntryPublic]
    count: int


class CommunityLeaderboardListQuery(SQLModel):
    sort_by: CommunityLeaderboardSortBy = "views_count"
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)
    include_count: bool = True
