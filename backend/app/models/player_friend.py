from datetime import datetime, timedelta

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index
from sqlmodel import Field, SQLModel

from .player import PlayerFriendsVisibility, PlayerPublic

PLAYER_FRIEND_SYNC_COOLDOWN = timedelta(minutes=1)


class PlayerFriend(SQLModel, table=True):
    __tablename__ = "player_friend"
    __table_args__ = (
        Index("ix_player_friend_friend_steamid64", "friend_steamid64"),
    )

    player_steamid64: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("player.steamid64", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    friend_steamid64: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("player.steamid64", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    friend_since: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class PlayerFriendSyncPublic(SQLModel):
    visibility: PlayerFriendsVisibility | None = None
    last_checked_at: datetime | None = None
    last_attempted_at: datetime | None = None
    next_allowed_at: datetime | None = None


class PlayerFriendsPublic(SQLModel):
    data: list[PlayerPublic]
    count: int
    sync: PlayerFriendSyncPublic


class PlayerFriendSyncResult(SQLModel):
    kind: str
    synced_count: int = 0
    next_allowed_at: datetime | None = None
    visibility: PlayerFriendsVisibility | None = None
