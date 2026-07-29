from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, update
from sqlmodel import col

from app.core.db import async_session_maker
from app.crud.player import (
    _fetch_players_from_steam_api_if_available,
    create_or_update_player_from_steam_data_if_fetched,
    get_player_by_steamid64,
    notify_player_steam_profile_updated,
    update_player_identity_fields,
)
from app.models import Player

STEAM_PROFILE_SYNC_INTERVAL = timedelta(days=7)
STEAM_PROFILE_SYNC_RETRY_INTERVAL = timedelta(hours=1)
STEAM_PROFILE_FETCH_BATCH_SIZE = 100


def is_player_steam_profile_sync_due(*, player: Player, now: datetime) -> bool:
    attempted_at = player.steam_profile_sync_attempted_at
    if (
        attempted_at is not None
        and attempted_at > now - STEAM_PROFILE_SYNC_RETRY_INTERVAL
    ):
        return False
    if player.steam_profile_synced_at is None:
        return True
    return bool(player.steam_profile_synced_at <= now - STEAM_PROFILE_SYNC_INTERVAL)


async def sync_player_steam_profile_if_due(*, steamid64: int) -> None:
    await sync_player_steam_profiles_if_due(steamid64s=[steamid64])


def _identity_fields(player: Player) -> tuple[str, str | None, str | None, str | None]:
    return (player.name, player.custom_id, player.avatar_hash, player.country)


async def sync_player_steam_profiles_if_due(*, steamid64s: Sequence[int]) -> None:
    """
    Claim and refresh Steam profiles outside the request path.

    The claim update is committed before calling Steam so concurrent requests can
    schedule this freely while only one worker performs the external request.
    A successful Steam response with no matching player writes an empty string as
    an avatar sentinel. Transport/API failures leave profile fields unchanged and
    retry after a short cooldown; successful responses remain fresh for seven days.
    """
    unique_steamid64s = list(dict.fromkeys(steamid64s))
    if not unique_steamid64s:
        return

    now = datetime.now(UTC)
    stale_before = now - STEAM_PROFILE_SYNC_INTERVAL
    retry_before = now - STEAM_PROFILE_SYNC_RETRY_INTERVAL
    async with async_session_maker() as session:
        try:
            claim_statement = (
                update(Player)
                .where(
                    col(Player.steamid64).in_(unique_steamid64s),
                    and_(
                        or_(
                            col(Player.steam_profile_sync_attempted_at).is_(None),
                            col(Player.steam_profile_sync_attempted_at) <= retry_before,
                        ),
                        or_(
                            col(Player.steam_profile_synced_at).is_(None),
                            col(Player.steam_profile_synced_at) <= stale_before,
                        ),
                    ),
                )
                .values(
                    steam_profile_sync_attempted_at=now,
                    updated_at=now,
                )
                .returning(col(Player.steamid64))
            )
            claimed_steamid64s = list(
                (await session.execute(claim_statement)).scalars().all()
            )
            await session.commit()
            session.expunge_all()

            if not claimed_steamid64s:
                return

            for batch_start in range(
                0, len(claimed_steamid64s), STEAM_PROFILE_FETCH_BATCH_SIZE
            ):
                batch_steamid64s = claimed_steamid64s[
                    batch_start : batch_start + STEAM_PROFILE_FETCH_BATCH_SIZE
                ]
                steam_data_by_steamid64 = (
                    await _fetch_players_from_steam_api_if_available(batch_steamid64s)
                )
                if steam_data_by_steamid64 is None:
                    continue

                for steamid64 in batch_steamid64s:
                    player = await get_player_by_steamid64(
                        session=session, steamid64=steamid64
                    )
                    if player is None:
                        continue
                    previous_identity = _identity_fields(player)
                    steam_data = steam_data_by_steamid64.get(steamid64)
                    if steam_data is None:
                        now = datetime.now(UTC)
                        await update_player_identity_fields(
                            session=session,
                            player=player,
                            avatar_hash="",
                            now=now,
                        )
                    else:
                        (
                            player,
                            _,
                        ) = await create_or_update_player_from_steam_data_if_fetched(
                            session=session,
                            steamid64=steamid64,
                            steam_data=steam_data,
                        )
                        if player is None:
                            continue

                    player.steam_profile_synced_at = datetime.now(UTC)
                    session.add(player)
                    if _identity_fields(player) != previous_identity:
                        await notify_player_steam_profile_updated(
                            session=session,
                            steamid64=steamid64,
                        )
                    await session.commit()
        finally:
            session.expunge_all()
