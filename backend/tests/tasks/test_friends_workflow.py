"""Bulk friend synchronization aggregates outcomes and preserves interrupted progress."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import LeaderboardPlayer, ModeScope, Player
from app.tasks import friends
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


async def test_bulk_friends_sync_counts_private_failed_and_rate_limited_players(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @asynccontextmanager
    async def session_factory():
        yield db

    monkeypatch.setattr(friends, "async_session_maker", session_factory)
    ids = [random_steamid64() for _ in range(6)]
    db.add_all(
        [
            Player(steamid64=steamid, name=f"Friend {index}")
            for index, steamid in enumerate(ids[:-1])
        ]
    )
    await db.flush()
    db.add(LeaderboardPlayer(steamid64=ids[0], scope=ModeScope.OVR, rating=10))
    await db.flush()
    assert await friends.load_target_steamid64s(steamid64s=[ids[0], ids[0]]) == [ids[0]]
    assert ids[0] in await friends.load_target_steamid64s(
        leaderboard_scope=ModeScope.OVR
    )
    assert set(ids[:-1]).issubset(await friends.load_target_steamid64s())
    sync = AsyncMock(
        side_effect=[
            SimpleNamespace(kind=kind)
            for kind in [
                "success",
                "rate_limited",
                "private_profile",
                "private_friends",
                "failed",
            ]
        ]
    )
    monkeypatch.setattr(friends, "sync_player_friends", sync)
    result = await friends.sync_player_friends_for_players(steamid64s=ids)
    assert (
        result.selected,
        result.synced,
        result.rate_limited,
        result.private,
        result.failed,
    ) == (6, 1, 1, 2, 2)
    sync.side_effect = KeyboardInterrupt()
    with pytest.raises(friends.SyncPlayerFriendsInterruptedError) as interrupted:
        await friends.sync_player_friends_for_players(steamid64s=ids, limit=2)
    assert interrupted.value.result.selected == 2
    assert interrupted.value.result.synced == 0
    monkeypatch.setattr(friends, "load_target_steamid64s", AsyncMock(return_value=[]))
    assert (await friends.sync_player_friends_for_players()).selected == 0
