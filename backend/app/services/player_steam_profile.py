from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, update
from sqlmodel import col

from app.core.db import async_session_maker
from app.crud.player import (
    _fetch_players_from_steam_api_if_available,
    create_or_update_player_from_steam_data_if_fetched,
    get_player_by_steamid64,
    update_player_identity_fields,
)
from app.models import Player

STEAM_PROFILE_SYNC_INTERVAL = timedelta(days=7)


def is_player_steam_profile_sync_due(*, player: Player, now: datetime) -> bool:
    if player.steam_profile_synced_at is None:
        return True
    return bool(player.steam_profile_synced_at <= now - STEAM_PROFILE_SYNC_INTERVAL)


async def sync_player_steam_profile_if_due(*, steamid64: int) -> None:
    """
    Claim and refresh a player's Steam profile outside the request path.

    The claim update is committed before calling Steam so concurrent requests can
    schedule this freely while only one worker performs the external request.
    A successful Steam response with no matching player writes an empty string as
    an avatar sentinel. Transport/API failures leave profile fields unchanged,
    but the sync timestamp still throttles read-triggered retries for seven days.
    """
    now = datetime.now(UTC)
    stale_before = now - STEAM_PROFILE_SYNC_INTERVAL
    async with async_session_maker() as session:
        try:
            claim_statement = (
                update(Player)
                .where(
                    col(Player.steamid64) == steamid64,
                    or_(
                        col(Player.steam_profile_synced_at).is_(None),
                        col(Player.steam_profile_synced_at) <= stale_before,
                    ),
                )
                .values(
                    steam_profile_synced_at=now,
                    updated_at=now,
                )
                .returning(col(Player.steamid64))
            )
            claimed_steamid64 = (
                await session.execute(claim_statement)
            ).scalar_one_or_none()
            await session.commit()
            session.expunge_all()

            if claimed_steamid64 is None:
                return

            steam_data_by_steamid64 = await _fetch_players_from_steam_api_if_available(
                [steamid64],
            )
            if steam_data_by_steamid64 is None:
                return

            steam_data = steam_data_by_steamid64.get(steamid64)
            if steam_data is None:
                player = await get_player_by_steamid64(
                    session=session, steamid64=steamid64
                )
                if player is not None:
                    now = datetime.now(UTC)
                    await update_player_identity_fields(
                        session=session,
                        player=player,
                        avatar_hash="",
                        now=now,
                    )
                    session.add(player)
                    await session.commit()
                return

            await create_or_update_player_from_steam_data_if_fetched(
                session=session,
                steamid64=steamid64,
                steam_data=steam_data,
            )
        finally:
            session.expunge_all()
