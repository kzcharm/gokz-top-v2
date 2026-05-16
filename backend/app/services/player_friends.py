from datetime import UTC, datetime
from math import ceil

import httpx
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.models import (
    PLAYER_FRIEND_SYNC_COOLDOWN,
    Player,
    PlayerAction,
    PlayerFriendsPublic,
    PlayerFriendsVisibility,
    PlayerFriendSyncPublic,
    PlayerFriendSyncResult,
)

STEAM_API_TIMEOUT_SECONDS = 10.0


class SteamFriendsPrivateError(Exception):
    pass


def format_friends_sync_retry_wait(
    *,
    now: datetime,
    next_allowed_at: datetime | None,
) -> str:
    if next_allowed_at is None:
        return "1 second"

    remaining_seconds = max(ceil((next_allowed_at - now).total_seconds()), 1)
    if remaining_seconds >= 86400:
        value = ceil(remaining_seconds / 86400)
        unit = "day"
    elif remaining_seconds >= 3600:
        value = ceil(remaining_seconds / 3600)
        unit = "hour"
    elif remaining_seconds >= 60:
        value = ceil(remaining_seconds / 60)
        unit = "minute"
    else:
        value = remaining_seconds
        unit = "second"

    suffix = "" if value == 1 else "s"
    return f"{value} {unit}{suffix}"


async def _fetch_steam_profile_is_public(*, steamid64: int) -> bool | None:
    if not settings.STEAM_API_KEY:
        return None

    params = {
        "key": settings.STEAM_API_KEY,
        "steamids": str(steamid64),
    }

    try:
        async with httpx.AsyncClient(timeout=STEAM_API_TIMEOUT_SECONDS) as client:
            response = await client.get(
                "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/",
                params=params,
            )
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return None

    players = payload.get("response", {}).get("players", [])
    if not isinstance(players, list) or not players:
        return None
    player = players[0]
    if not isinstance(player, dict):
        return None

    visibility = player.get("communityvisibilitystate")
    try:
        return int(visibility) >= 3
    except (TypeError, ValueError):
        return None


async def _fetch_steam_friends(
    *,
    steamid64: int,
) -> list[tuple[int, datetime | None]]:
    if not settings.STEAM_API_KEY:
        raise RuntimeError("STEAM_API_KEY is not configured")

    params = {
        "key": settings.STEAM_API_KEY,
        "steamid": str(steamid64),
        "relationship": "friend",
    }

    async with httpx.AsyncClient(timeout=STEAM_API_TIMEOUT_SECONDS) as client:
        response = await client.get(
            "https://api.steampowered.com/ISteamUser/GetFriendList/v1/",
            params=params,
        )
        if response.status_code == 401:
            raise SteamFriendsPrivateError("Friends list is private")
        response.raise_for_status()
        payload = response.json()

    friends = payload.get("friendslist", {}).get("friends", [])
    if not isinstance(friends, list):
        return []

    results: list[tuple[int, datetime | None]] = []
    for raw_friend in friends:
        if not isinstance(raw_friend, dict):
            continue
        try:
            friend_steamid64 = int(raw_friend["steamid"])
        except (KeyError, TypeError, ValueError):
            continue

        friend_since_raw = raw_friend.get("friend_since")
        friend_since: datetime | None = None
        if friend_since_raw is not None:
            try:
                friend_since = datetime.fromtimestamp(int(friend_since_raw), UTC)
            except (OverflowError, TypeError, ValueError):
                friend_since = None

        results.append((friend_steamid64, friend_since))

    return results


async def build_player_friend_sync_public(
    *,
    session: AsyncSession,
    player: Player,
    now: datetime | None = None,
) -> PlayerFriendSyncPublic:
    resolved_now = now or datetime.now(UTC)
    action_timestamp = await crud.get_player_action_timestamp(
        session=session,
        player_steamid64=player.steamid64,
        action=PlayerAction.FRIENDS_SYNC,
    )
    next_allowed_at: datetime | None = None
    if action_timestamp is not None:
        candidate = action_timestamp.recorded_at + PLAYER_FRIEND_SYNC_COOLDOWN
        if candidate > resolved_now:
            next_allowed_at = candidate

    return PlayerFriendSyncPublic(
        visibility=player.friends_visibility,
        last_checked_at=player.friends_visibility_checked_at,
        last_attempted_at=(
            action_timestamp.recorded_at if action_timestamp is not None else None
        ),
        next_allowed_at=next_allowed_at,
    )


async def read_player_friends_public(
    *,
    session: AsyncSession,
    player: Player,
) -> PlayerFriendsPublic:
    friends, count = await crud.get_player_friends(
        session=session,
        player_steamid64=player.steamid64,
    )
    return PlayerFriendsPublic(
        data=await crud.to_player_publics(session=session, players=friends),
        count=count,
        sync=await build_player_friend_sync_public(session=session, player=player),
    )


async def sync_player_friends(
    *,
    session: AsyncSession,
    player: Player,
) -> PlayerFriendSyncResult:
    now = datetime.now(UTC)
    claim = await crud.claim_player_action_timestamp(
        session=session,
        player_steamid64=player.steamid64,
        action=PlayerAction.FRIENDS_SYNC,
        recorded_at=now,
        cooldown=PLAYER_FRIEND_SYNC_COOLDOWN,
    )
    await session.commit()

    if not claim.claimed:
        return PlayerFriendSyncResult(
            kind="rate_limited",
            next_allowed_at=claim.next_available_at,
            visibility=player.friends_visibility,
        )

    is_public = await _fetch_steam_profile_is_public(steamid64=player.steamid64)
    if is_public is None:
        return PlayerFriendSyncResult(kind="failed", visibility=player.friends_visibility)
    if not is_public:
        player.friends_visibility = PlayerFriendsVisibility.PRIVATE_PROFILE
        player.friends_visibility_checked_at = now
        session.add(player)
        await session.commit()
        await session.refresh(player)
        return PlayerFriendSyncResult(
            kind="private_profile",
            visibility=player.friends_visibility,
        )

    try:
        steam_friends = await _fetch_steam_friends(steamid64=player.steamid64)
    except SteamFriendsPrivateError:
        player.friends_visibility = PlayerFriendsVisibility.PRIVATE_FRIENDS
        player.friends_visibility_checked_at = now
        session.add(player)
        await session.commit()
        await session.refresh(player)
        return PlayerFriendSyncResult(
            kind="private_friends",
            visibility=player.friends_visibility,
        )
    except Exception:
        return PlayerFriendSyncResult(kind="failed", visibility=player.friends_visibility)

    steam_friend_ids = {
        friend_steamid64
        for friend_steamid64, _ in steam_friends
        if friend_steamid64 != player.steamid64
    }
    existing_player_ids: set[int] = set()
    if steam_friend_ids:
        statement = select(Player.steamid64).where(col(Player.steamid64).in_(steam_friend_ids))
        existing_player_ids = set((await session.exec(statement)).all())

    kz_friends = [
        (friend_steamid64, friend_since)
        for friend_steamid64, friend_since in steam_friends
        if friend_steamid64 in existing_player_ids and friend_steamid64 != player.steamid64
    ]
    desired_friend_ids = {friend_steamid64 for friend_steamid64, _ in kz_friends}
    current_friend_ids = await crud.get_player_friend_steamid64s(
        session=session,
        player_steamid64=player.steamid64,
    )

    upsert_edges = []
    for friend_steamid64, friend_since in kz_friends:
        upsert_edges.append((player.steamid64, friend_steamid64, friend_since))
        upsert_edges.append((friend_steamid64, player.steamid64, friend_since))
    await crud.upsert_player_friend_edges(session=session, edges=upsert_edges)

    stale_friend_ids = current_friend_ids - desired_friend_ids
    delete_edges = []
    for friend_steamid64 in stale_friend_ids:
        delete_edges.append((player.steamid64, friend_steamid64))
        delete_edges.append((friend_steamid64, player.steamid64))
    await crud.delete_player_friend_edges(session=session, edges=delete_edges)

    player.friends_visibility = PlayerFriendsVisibility.PUBLIC
    player.friends_visibility_checked_at = now
    session.add(player)
    await session.commit()
    await session.refresh(player)

    return PlayerFriendSyncResult(
        kind="success",
        synced_count=len(desired_friend_ids),
        visibility=player.friends_visibility,
    )
