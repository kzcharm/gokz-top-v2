import uuid
from datetime import datetime, timedelta

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import col
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    Player,
    PlayerSession,
    PlayerSessionConnect,
    PlayerSessionDisconnect,
    PlayerSessionHeartbeat,
    PlayerSessionPublic,
    ServerGroup,
)
from app.services.geoip import lookup_geoip_city


def to_player_session_public(*, player_session: PlayerSession) -> PlayerSessionPublic:
    return PlayerSessionPublic(
        id=player_session.id,
        player_steamid64=str(player_session.player_steamid64),
        server_group_id=player_session.server_group_id,
        connected_at=player_session.connected_at,
        disconnect_at=player_session.disconnect_at,
        last_heartbeat_at=player_session.last_heartbeat_at,
        ip_address=str(player_session.ip_address),
        map_name=player_session.map_name,
        duration_seconds=player_session.duration_seconds,
    )


async def get_player_session_by_id(
    *,
    session: AsyncSession,
    session_id: uuid.UUID,
) -> PlayerSession | None:
    return await session.get(PlayerSession, session_id)


async def _ensure_player_for_session(
    *,
    session: AsyncSession,
    steamid64: int,
    now: datetime,
    ip_address: str,
) -> None:
    location = lookup_geoip_city(ip_address)
    country = location.country_code if location is not None else None
    player_table = Player.__table__  # type: ignore[attr-defined]
    insert_statement = pg_insert(player_table).values(
        steamid64=steamid64,
        name=str(steamid64),
        country=country,
        created_at=now,
        updated_at=now,
    )
    if country is None:
        await session.exec(insert_statement.on_conflict_do_nothing())
        return

    await session.exec(
        insert_statement.on_conflict_do_update(
            index_elements=[player_table.c.steamid64],
            set_={
                "country": country,
                "updated_at": now,
            },
            where=player_table.c.is_country_locked.is_(False),
        )
    )


def _same_connect_identity(
    *,
    player_session: PlayerSession,
    group: ServerGroup,
    player_steamid64: int,
) -> bool:
    return (
        player_session.server_group_id == group.id
        and player_session.player_steamid64 == player_steamid64
    )


async def connect_player_session(
    *,
    session: AsyncSession,
    group: ServerGroup,
    payload: PlayerSessionConnect,
) -> PlayerSession:
    player_steamid64 = int(payload.player_steamid64)
    existing = await get_player_session_by_id(
        session=session,
        session_id=payload.session_id,
    )
    if existing is not None:
        if _same_connect_identity(
            player_session=existing,
            group=group,
            player_steamid64=player_steamid64,
        ):
            return existing
        raise ValueError("Player session already exists")

    await _ensure_player_for_session(
        session=session,
        steamid64=player_steamid64,
        now=payload.connected_at,
        ip_address=str(payload.ip_address),
    )
    player_session = PlayerSession(
        id=payload.session_id,
        player_steamid64=player_steamid64,
        server_group_id=group.id,
        connected_at=payload.connected_at,
        last_heartbeat_at=payload.connected_at,
        ip_address=str(payload.ip_address),
        map_name=payload.map_name,
    )
    session.add(player_session)
    await session.commit()
    await session.refresh(player_session)
    return player_session


async def heartbeat_player_session(
    *,
    session: AsyncSession,
    group: ServerGroup,
    payload: PlayerSessionHeartbeat,
) -> PlayerSession | None:
    player_session = await get_player_session_by_id(
        session=session,
        session_id=payload.session_id,
    )
    if player_session is None:
        return None
    if player_session.server_group_id != group.id:
        raise PermissionError("Player session does not belong to this server group")
    if player_session.disconnect_at is not None:
        return player_session
    if payload.heartbeat_at < player_session.connected_at:
        raise ValueError("heartbeat_at must not be before connected_at")
    if payload.heartbeat_at <= player_session.last_heartbeat_at:
        return player_session

    player_session.last_heartbeat_at = payload.heartbeat_at
    session.add(player_session)
    await session.commit()
    await session.refresh(player_session)
    return player_session


async def disconnect_player_session(
    *,
    session: AsyncSession,
    group: ServerGroup,
    payload: PlayerSessionDisconnect,
) -> PlayerSession | None:
    player_session = await get_player_session_by_id(
        session=session,
        session_id=payload.session_id,
    )
    if player_session is None:
        return None
    if player_session.server_group_id != group.id:
        raise PermissionError("Player session does not belong to this server group")
    if player_session.disconnect_at is not None:
        return player_session
    if payload.disconnect_at < player_session.connected_at:
        raise ValueError("disconnect_at must not be before connected_at")

    player_session.disconnect_at = payload.disconnect_at
    if payload.disconnect_at > player_session.last_heartbeat_at:
        player_session.last_heartbeat_at = payload.disconnect_at
    session.add(player_session)
    await session.commit()
    await session.refresh(player_session)
    return player_session


async def close_timed_out_player_sessions(
    *,
    session: AsyncSession,
    now: datetime,
    timeout: timedelta,
) -> int:
    cutoff = now - timeout
    statement = (
        update(PlayerSession)
        .where(
            col(PlayerSession.disconnect_at).is_(None),
            col(PlayerSession.last_heartbeat_at) < cutoff,
        )
        .values(disconnect_at=PlayerSession.last_heartbeat_at)
    )
    result = await session.exec(statement)
    await session.commit()
    return int(result.rowcount or 0)


__all__ = [
    "close_timed_out_player_sessions",
    "connect_player_session",
    "disconnect_player_session",
    "get_player_session_by_id",
    "heartbeat_player_session",
    "to_player_session_public",
]
