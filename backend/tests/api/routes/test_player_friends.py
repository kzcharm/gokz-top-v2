from datetime import UTC, datetime, timedelta

import httpx
import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import (
    Player,
    PlayerAction,
    PlayerActionTimestamp,
    PlayerFriend,
    PlayerFriendsVisibility,
)
from app.services import player_friends
from tests.utils.user import authentication_token_from_steamid
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


async def _create_player(
    db: AsyncSession,
    *,
    steamid64: int,
    name: str,
    friends_visibility: PlayerFriendsVisibility | None = None,
    friends_visibility_checked_at: datetime | None = None,
) -> Player:
    player = Player(
        steamid64=steamid64,
        name=name,
        friends_visibility=friends_visibility,
        friends_visibility_checked_at=friends_visibility_checked_at,
    )
    db.add(player)
    await db.commit()
    await db.refresh(player)
    return player


async def _insert_friendship(
    db: AsyncSession,
    *,
    player_steamid64: int,
    friend_steamid64: int,
) -> None:
    db.add(
        PlayerFriend(
            player_steamid64=player_steamid64,
            friend_steamid64=friend_steamid64,
        )
    )
    await db.commit()


async def _set_friends_sync_timestamp(
    db: AsyncSession,
    *,
    steamid64: int,
    recorded_at: datetime,
) -> None:
    db.add(
        PlayerActionTimestamp(
            player_steamid64=steamid64,
            action=PlayerAction.FRIENDS_SYNC,
            recorded_at=recorded_at,
        )
    )
    await db.commit()


async def test_read_player_friends_returns_public_sync_metadata(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    owner = await _create_player(
        db,
        steamid64=random_steamid64(),
        name="Owner",
        friends_visibility=PlayerFriendsVisibility.PUBLIC,
        friends_visibility_checked_at=datetime.now(UTC) - timedelta(seconds=10),
    )
    friend = await _create_player(
        db,
        steamid64=random_steamid64(),
        name="Friend",
    )
    await _insert_friendship(
        db,
        player_steamid64=owner.steamid64,
        friend_steamid64=friend.steamid64,
    )
    await _set_friends_sync_timestamp(
        db,
        steamid64=owner.steamid64,
        recorded_at=datetime.now(UTC) - timedelta(seconds=20),
    )

    response = await client.get(
        f"{settings.API_V1_STR}/players/{owner.steamid64}/friends"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["data"][0]["steamid64"] == str(friend.steamid64)
    assert payload["sync"]["visibility"] == "public"
    assert payload["sync"]["last_attempted_at"] is not None
    assert payload["sync"]["next_allowed_at"] is not None


async def test_sync_player_friends_reconciles_known_friends_and_deletes_stale_edges(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await _create_player(db, steamid64=random_steamid64(), name="Owner")
    current_friend = await _create_player(
        db,
        steamid64=random_steamid64(),
        name="Current Friend",
    )
    stale_friend = await _create_player(
        db,
        steamid64=random_steamid64(),
        name="Stale Friend",
    )
    missing_friend = random_steamid64()

    await _insert_friendship(
        db,
        player_steamid64=owner.steamid64,
        friend_steamid64=stale_friend.steamid64,
    )
    await _insert_friendship(
        db,
        player_steamid64=stale_friend.steamid64,
        friend_steamid64=owner.steamid64,
    )

    async def _public_profile(*, steamid64: int) -> bool | None:
        assert steamid64 == owner.steamid64
        return True

    async def _fetch_friends(*, steamid64: int) -> list[tuple[int, datetime | None]]:
        assert steamid64 == owner.steamid64
        return [
            (current_friend.steamid64, datetime(2026, 5, 1, tzinfo=UTC)),
            (missing_friend, datetime(2026, 5, 2, tzinfo=UTC)),
        ]

    monkeypatch.setattr(player_friends, "_fetch_steam_profile_is_public", _public_profile)
    monkeypatch.setattr(player_friends, "_fetch_steam_friends", _fetch_friends)

    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=owner.steamid64,
        db=db,
    )
    response = await client.post(
        f"{settings.API_V1_STR}/players/{owner.steamid64}/friends/sync",
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["data"][0]["steamid64"] == str(current_friend.steamid64)
    assert payload["sync"]["visibility"] == "public"

    assert await db.get(PlayerFriend, (owner.steamid64, current_friend.steamid64)) is not None
    assert await db.get(PlayerFriend, (current_friend.steamid64, owner.steamid64)) is not None
    assert await db.get(PlayerFriend, (owner.steamid64, stale_friend.steamid64)) is None
    assert await db.get(PlayerFriend, (stale_friend.steamid64, owner.steamid64)) is None
    assert await db.get(PlayerFriend, (owner.steamid64, missing_friend)) is None


async def test_sync_player_friends_private_result_preserves_existing_edges(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await _create_player(db, steamid64=random_steamid64(), name="Owner")
    stale_friend = await _create_player(
        db,
        steamid64=random_steamid64(),
        name="Existing Friend",
    )
    await _insert_friendship(
        db,
        player_steamid64=owner.steamid64,
        friend_steamid64=stale_friend.steamid64,
    )
    await _insert_friendship(
        db,
        player_steamid64=stale_friend.steamid64,
        friend_steamid64=owner.steamid64,
    )

    async def _public_profile(*, steamid64: int) -> bool | None:
        assert steamid64 == owner.steamid64
        return True

    async def _private_friends(*, steamid64: int) -> list[tuple[int, datetime | None]]:
        assert steamid64 == owner.steamid64
        raise player_friends.SteamFriendsPrivateError("private")

    monkeypatch.setattr(player_friends, "_fetch_steam_profile_is_public", _public_profile)
    monkeypatch.setattr(player_friends, "_fetch_steam_friends", _private_friends)

    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=owner.steamid64,
        db=db,
    )
    response = await client.post(
        f"{settings.API_V1_STR}/players/{owner.steamid64}/friends/sync",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["sync"]["visibility"] == "private_friends"
    assert await db.get(PlayerFriend, (owner.steamid64, stale_friend.steamid64)) is not None
    assert await db.get(PlayerFriend, (stale_friend.steamid64, owner.steamid64)) is not None


async def test_sync_player_friends_failed_fetch_preserves_existing_edges_and_returns_502(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await _create_player(db, steamid64=random_steamid64(), name="Owner")
    stale_friend = await _create_player(
        db,
        steamid64=random_steamid64(),
        name="Existing Friend",
    )
    await _insert_friendship(
        db,
        player_steamid64=owner.steamid64,
        friend_steamid64=stale_friend.steamid64,
    )
    await _insert_friendship(
        db,
        player_steamid64=stale_friend.steamid64,
        friend_steamid64=owner.steamid64,
    )

    async def _public_profile(*, steamid64: int) -> bool | None:
        assert steamid64 == owner.steamid64
        return True

    async def _timeout(*, steamid64: int) -> list[tuple[int, datetime | None]]:
        assert steamid64 == owner.steamid64
        raise httpx.ReadTimeout("timeout")

    monkeypatch.setattr(player_friends, "_fetch_steam_profile_is_public", _public_profile)
    monkeypatch.setattr(player_friends, "_fetch_steam_friends", _timeout)

    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=owner.steamid64,
        db=db,
    )
    response = await client.post(
        f"{settings.API_V1_STR}/players/{owner.steamid64}/friends/sync",
        headers=headers,
    )

    assert response.status_code == 502
    assert await db.get(PlayerFriend, (owner.steamid64, stale_friend.steamid64)) is not None
    assert await db.get(PlayerFriend, (stale_friend.steamid64, owner.steamid64)) is not None


async def test_sync_player_friends_returns_429_when_rate_limited(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    owner = await _create_player(db, steamid64=random_steamid64(), name="Owner")
    await _set_friends_sync_timestamp(
        db,
        steamid64=owner.steamid64,
        recorded_at=datetime.now(UTC),
    )

    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=owner.steamid64,
        db=db,
    )
    response = await client.post(
        f"{settings.API_V1_STR}/players/{owner.steamid64}/friends/sync",
        headers=headers,
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    assert (
        response.json()["detail"]
        == "Friends sync is rate limited. Wait 1 minute before retrying."
    )
