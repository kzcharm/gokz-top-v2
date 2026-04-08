from __future__ import annotations

import math
import uuid
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    Map,
    Server,
    ServerCreate,
    ServerGroup,
    ServerGroupCreate,
    ServerGroupStatus,
    ServerGroupSummary,
    ServerGroupUpdate,
    ServerHeartbeatRaw,
    ServerHeartbeatSource,
    ServerHistoryBucketPublic,
    ServerHistoryQuery,
    ServerListQuery,
    ServerLiveStatus,
    ServerLiveStatusPublic,
    ServerPublic,
    ServerSource,
    ServerStatusPut,
    ServerUpdate,
    get_datetime_utc,
)
from app.services.geoip import lookup_geoip_city

SERVER_STATUS_NOTIFY_CHANNEL = "server_status_updates"


def _normalize_server_location_value(value: str | None) -> str | None:
    if value is None:
        return None
    normalized_value = value.strip()
    return normalized_value or None


def _resolve_server_location(
    *,
    ip: str,
    country: str | None,
    city: str | None,
) -> tuple[str | None, str | None]:
    normalized_country = _normalize_server_location_value(country)
    normalized_city = _normalize_server_location_value(city)
    if normalized_country is not None and normalized_city is not None:
        return normalized_country, normalized_city

    location = lookup_geoip_city(ip)
    if location is None:
        return normalized_country, normalized_city

    return (
        normalized_country or location.country_code,
        normalized_city or location.city_name,
    )


def _build_server_live_status_public(
    status: ServerLiveStatus | None,
) -> ServerLiveStatusPublic | None:
    if status is None:
        return None
    return ServerLiveStatusPublic(
        current_hostname=status.current_hostname,
        map=status.map,
        player_count=status.player_count,
        max_players=status.max_players,
        players=status.players,
        is_online=status.is_online,
        last_plugin_seen_at=status.last_plugin_seen_at,
        last_a2s_seen_at=status.last_a2s_seen_at,
        last_successful_seen_at=status.last_successful_seen_at,
        updated_at=status.updated_at,
    )


def to_server_public(*, server: Server) -> ServerPublic:
    group = None
    loaded_group = server.__dict__.get("group")
    if isinstance(loaded_group, ServerGroup):
        group = ServerGroupSummary(id=loaded_group.id, name=loaded_group.name)

    loaded_status = server.__dict__.get("live_status")

    return ServerPublic(
        id=server.id,
        group_id=server.group_id,
        group=group,
        ip=server.ip,
        port=server.port,
        enabled=server.enabled,
        configured_hostname=server.configured_hostname,
        country=server.country,
        city=server.city,
        source=server.source,
        last_discovered_at=server.last_discovered_at,
        map_tier=server.__dict__.get("map_tier"),
        created_at=server.created_at,
        updated_at=server.updated_at,
        status=(
            _build_server_live_status_public(loaded_status)
            if isinstance(loaded_status, ServerLiveStatus)
            else None
        ),
    )


def generate_server_group_api_key() -> str:
    return str(uuid.uuid4())


def _should_auto_validate_server_group(
    *,
    group: ServerGroup | None,
    server: Server,
) -> bool:
    # The current autopilot rule validates on the first accepted plugin heartbeat
    # from an enabled server that belongs to the pending group.
    return (
        group is not None
        and group.status == ServerGroupStatus.PENDING
        and server.enabled
        and server.group_id == group.id
    )


async def notify_server_status_updated(
    *,
    session: AsyncSession,
    server_id: uuid.UUID,
) -> None:
    await session.execute(
        text(f"SELECT pg_notify('{SERVER_STATUS_NOTIFY_CHANNEL}', :server_id)"),
        {"server_id": str(server_id)},
    )


async def get_server_group_by_id(
    *,
    session: AsyncSession,
    group_id: uuid.UUID,
) -> ServerGroup | None:
    return await session.get(ServerGroup, group_id)


async def get_server_group_by_api_key(
    *,
    session: AsyncSession,
    api_key: str,
) -> ServerGroup | None:
    statement = select(ServerGroup).where(ServerGroup.api_key == api_key)
    return (await session.exec(statement)).first()


async def owner_has_invalidated_server_group(
    *,
    session: AsyncSession,
    owner_steamid64: int,
) -> bool:
    statement = select(ServerGroup.id).where(
        ServerGroup.owner_steamid64 == owner_steamid64,
        ServerGroup.status == ServerGroupStatus.INVALIDATED,
    )
    return (await session.exec(statement)).first() is not None


async def read_server_groups(
    *, session: AsyncSession
) -> tuple[list[ServerGroup], dict[uuid.UUID, int]]:
    groups_statement = select(ServerGroup).order_by(col(ServerGroup.name).asc())
    groups = list((await session.exec(groups_statement)).all())

    servers_statement = select(Server).where(col(Server.group_id).is_not(None))
    servers = list((await session.exec(servers_statement)).all())
    counts: dict[uuid.UUID, int] = {}
    for server in servers:
        if server.group_id is None:
            continue
        counts[server.group_id] = counts.get(server.group_id, 0) + 1
    return groups, counts


async def create_server_group(
    *,
    session: AsyncSession,
    group_in: ServerGroupCreate,
    owner_steamid64: int,
) -> tuple[ServerGroup, str]:
    if await owner_has_invalidated_server_group(
        session=session,
        owner_steamid64=owner_steamid64,
    ):
        raise ValueError("Server group owner is permanently blocked")

    api_key = generate_server_group_api_key()
    now = get_datetime_utc()
    group = ServerGroup(
        name=group_in.name,
        api_key=api_key,
        owner_steamid64=owner_steamid64,
        status=ServerGroupStatus.PENDING,
        created_at=now,
        updated_at=now,
    )
    session.add(group)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ValueError("Server group already exists") from exc
    await session.refresh(group)
    return group, api_key


async def update_server_group(
    *,
    session: AsyncSession,
    group: ServerGroup,
    group_in: ServerGroupUpdate,
) -> ServerGroup:
    group_data = group_in.model_dump(exclude_unset=True)
    previous_status = group.status
    group.sqlmodel_update(group_data)
    now = get_datetime_utc()
    group.updated_at = now
    session.add(group)
    if (
        previous_status != ServerGroupStatus.INVALIDATED
        and group.status == ServerGroupStatus.INVALIDATED
    ):
        statement = select(Server).where(Server.group_id == group.id)
        servers = list((await session.exec(statement)).all())
        for server in servers:
            if not server.enabled:
                continue
            server.enabled = False
            server.updated_at = now
            session.add(server)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ValueError("Server group already exists") from exc
    await session.refresh(group)
    return group


async def delete_server_group(*, session: AsyncSession, group: ServerGroup) -> None:
    statement = select(Server).where(Server.group_id == group.id)
    servers = list((await session.exec(statement)).all())
    now = get_datetime_utc()
    for server in servers:
        server.group_id = None
        server.updated_at = now
        session.add(server)
    await session.delete(group)
    await session.commit()


async def rotate_server_group_api_key(
    *,
    session: AsyncSession,
    group: ServerGroup,
) -> tuple[ServerGroup, str]:
    api_key = generate_server_group_api_key()
    now = get_datetime_utc()
    group.api_key = api_key
    group.updated_at = now
    session.add(group)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ValueError("Server group already exists") from exc
    await session.refresh(group)
    return group, api_key


async def get_server_by_id(
    *,
    session: AsyncSession,
    server_id: uuid.UUID,
    include_invalidated_group: bool = False,
) -> Server | None:
    statement = select(Server).where(col(Server.id) == server_id)
    server = (await session.exec(statement)).first()
    if server is None:
        return None
    await _hydrate_servers(session=session, servers=[server])
    if (
        not include_invalidated_group
        and server.group is not None
        and server.group.status == ServerGroupStatus.INVALIDATED
    ):
        return None
    return server


async def get_server_by_endpoint(
    *,
    session: AsyncSession,
    ip: str,
    port: int,
    hydrate: bool = True,
) -> Server | None:
    statement = select(Server).where(col(Server.ip) == ip, col(Server.port) == port)
    server = (await session.exec(statement)).first()
    if server is None:
        return None
    if hydrate:
        await _hydrate_servers(session=session, servers=[server])
    return server


async def read_servers(
    *,
    session: AsyncSession,
    query: ServerListQuery,
) -> tuple[list[Server], int]:
    statement = select(Server)
    if query.group_id is not None:
        statement = statement.where(col(Server.group_id) == query.group_id)
    if query.country:
        statement = statement.where(col(Server.country) == query.country.upper())
    if query.city:
        statement = statement.where(col(Server.city) == query.city)
    if query.source is not None:
        statement = statement.where(col(Server.source) == query.source)
    servers = list((await session.exec(statement)).all())
    await _hydrate_servers(session=session, servers=servers)
    servers = [
        server
        for server in servers
        if not (
            server.group is not None
            and server.group.status == ServerGroupStatus.INVALIDATED
        )
    ]

    if query.online is not None:
        servers = [
            server
            for server in servers
            if (
                (server.live_status.is_online if server.live_status else False)
                == query.online
            )
        ]

    servers.sort(
        key=lambda server: (
            0 if server.live_status and server.live_status.is_online else 1,
            (server.live_status.current_hostname if server.live_status else None)
            or server.configured_hostname
            or "",
            server.ip,
            server.port,
        )
    )

    count = len(servers)
    return servers[query.offset : query.offset + query.limit], count


async def _validate_group_id(
    *,
    session: AsyncSession,
    group_id: uuid.UUID | None,
) -> None:
    if group_id is None:
        return
    group = await get_server_group_by_id(session=session, group_id=group_id)
    if group is None:
        raise ValueError("Server group not found")


async def create_server(
    *,
    session: AsyncSession,
    server_in: ServerCreate,
    queried_hostname: str,
    queried_map: str,
    queried_player_count: int,
    queried_max_players: int,
    queried_players: list[dict[str, Any]],
) -> Server:
    await _validate_group_id(session=session, group_id=server_in.group_id)

    now = get_datetime_utc()
    resolved_country, resolved_city = _resolve_server_location(
        ip=server_in.ip,
        country=server_in.country,
        city=server_in.city,
    )
    server = Server(
        group_id=server_in.group_id,
        ip=server_in.ip,
        port=server_in.port,
        enabled=server_in.enabled,
        configured_hostname=queried_hostname,
        country=resolved_country,
        city=resolved_city,
        source=ServerSource.MANUAL,
        created_at=now,
        updated_at=now,
    )
    session.add(server)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ValueError("Server already exists") from exc

    await _record_server_status(
        session=session,
        server=server,
        source=ServerHeartbeatSource.A2S,
        observed_at=now,
        hostname=queried_hostname,
        map_name=queried_map,
        player_count=queried_player_count,
        max_players=queried_max_players,
        players=queried_players,
        is_online=True,
    )
    await notify_server_status_updated(session=session, server_id=server.id)
    await session.commit()
    await session.refresh(server)
    return await get_server_by_id(session=session, server_id=server.id) or server


async def update_server(
    *,
    session: AsyncSession,
    server: Server,
    server_in: ServerUpdate,
) -> Server:
    update_data = server_in.model_dump(exclude_unset=True)
    if "group_id" in update_data:
        await _validate_group_id(session=session, group_id=update_data["group_id"])
    server.sqlmodel_update(update_data)
    server.country, server.city = _resolve_server_location(
        ip=server.ip,
        country=server.country,
        city=server.city,
    )
    server.updated_at = get_datetime_utc()
    session.add(server)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ValueError("Server already exists") from exc
    await session.refresh(server)
    return await get_server_by_id(session=session, server_id=server.id) or server


async def delete_server(*, session: AsyncSession, server: Server) -> None:
    await session.delete(server)
    await session.commit()


async def upsert_discovered_server(
    *,
    session: AsyncSession,
    ip: str,
    port: int,
    hostname: str,
    map_name: str,
    player_count: int,
    max_players: int,
    players: list[dict[str, Any]],
    observed_at: datetime,
    commit: bool = True,
) -> Server:
    server = await get_server_by_endpoint(
        session=session,
        ip=ip,
        port=port,
        hydrate=False,
    )
    now = observed_at
    if server is None:
        resolved_country, resolved_city = _resolve_server_location(
            ip=ip,
            country=None,
            city=None,
        )
        server = Server(
            ip=ip,
            port=port,
            enabled=True,
            configured_hostname=hostname,
            country=resolved_country,
            city=resolved_city,
            source=ServerSource.STEAM_MASTER,
            last_discovered_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(server)
        await session.flush()
    else:
        if server.configured_hostname is None:
            server.configured_hostname = hostname
        if server.source == ServerSource.STEAM_MASTER:
            server.enabled = True
        server.country, server.city = _resolve_server_location(
            ip=ip,
            country=server.country,
            city=server.city,
        )
        server.last_discovered_at = now
        server.updated_at = now
        session.add(server)

    await _record_server_status(
        session=session,
        server=server,
        source=ServerHeartbeatSource.A2S,
        observed_at=observed_at,
        hostname=hostname,
        map_name=map_name,
        player_count=player_count,
        max_players=max_players,
        players=players,
        is_online=True,
    )
    await notify_server_status_updated(session=session, server_id=server.id)
    if commit:
        await session.commit()
        await session.refresh(server)
        return await get_server_by_id(session=session, server_id=server.id) or server
    return server


async def record_plugin_heartbeat(
    *,
    session: AsyncSession,
    group: ServerGroup | None = None,
    server: Server,
    payload: ServerStatusPut,
) -> Server:
    await _record_server_status(
        session=session,
        server=server,
        source=ServerHeartbeatSource.PLUGIN,
        observed_at=payload.observed_at,
        hostname=payload.hostname,
        map_name=payload.map,
        player_count=payload.player_count,
        max_players=payload.max_players,
        players=payload.players,
        is_online=True,
    )
    if _should_auto_validate_server_group(group=group, server=server):
        group.status = ServerGroupStatus.VALIDATED
        group.updated_at = payload.observed_at
        session.add(group)
    await notify_server_status_updated(session=session, server_id=server.id)
    await session.commit()
    return await get_server_by_id(session=session, server_id=server.id) or server


async def record_a2s_success(
    *,
    session: AsyncSession,
    server: Server,
    observed_at: datetime,
    hostname: str,
    map_name: str,
    player_count: int,
    max_players: int,
    players: list[dict[str, Any]],
) -> Server:
    await _record_server_status(
        session=session,
        server=server,
        source=ServerHeartbeatSource.A2S,
        observed_at=observed_at,
        hostname=hostname,
        map_name=map_name,
        player_count=player_count,
        max_players=max_players,
        players=players,
        is_online=True,
    )
    await notify_server_status_updated(session=session, server_id=server.id)
    await session.commit()
    return await get_server_by_id(session=session, server_id=server.id) or server


async def record_a2s_failure(
    *,
    session: AsyncSession,
    server: Server,
    observed_at: datetime,
    mark_offline: bool,
) -> Server:
    status = await _get_server_live_status(session=session, server=server)
    if status is None:
        status = ServerLiveStatus(server_id=server.id)
        session.add(status)
        server.live_status = status

    status.last_a2s_seen_at = observed_at
    status.current_hostname = status.current_hostname or server.configured_hostname
    session.add(status)

    if not status.is_online:
        await session.commit()
        return await get_server_by_id(session=session, server_id=server.id) or server
    if not mark_offline:
        await notify_server_status_updated(session=session, server_id=server.id)
        await session.commit()
        return await get_server_by_id(session=session, server_id=server.id) or server

    status.player_count = 0
    status.players = []
    status.is_online = False
    status.updated_at = observed_at
    session.add(status)

    heartbeat = ServerHeartbeatRaw(
        server_id=server.id,
        source=ServerHeartbeatSource.OFFLINE_MARK,
        observed_at=observed_at,
        hostname=status.current_hostname,
        map=status.map,
        player_count=0,
        max_players=status.max_players,
        players=[],
        is_online=False,
    )
    session.add(heartbeat)
    await notify_server_status_updated(session=session, server_id=server.id)
    await session.commit()
    return await get_server_by_id(session=session, server_id=server.id) or server


async def record_offline_mark(
    *,
    session: AsyncSession,
    server: Server,
    observed_at: datetime,
) -> Server:
    status = await _get_server_live_status(session=session, server=server)
    if status is None:
        status = ServerLiveStatus(server_id=server.id)
        session.add(status)
        server.live_status = status

    status.last_a2s_seen_at = observed_at
    status.current_hostname = status.current_hostname or server.configured_hostname
    status.player_count = 0
    status.players = []
    status.is_online = False
    status.updated_at = observed_at
    session.add(status)

    heartbeat = ServerHeartbeatRaw(
        server_id=server.id,
        source=ServerHeartbeatSource.OFFLINE_MARK,
        observed_at=observed_at,
        hostname=status.current_hostname,
        map=status.map,
        player_count=0,
        max_players=status.max_players,
        players=[],
        is_online=False,
    )
    session.add(heartbeat)
    await notify_server_status_updated(session=session, server_id=server.id)
    await session.commit()
    return await get_server_by_id(session=session, server_id=server.id) or server


async def read_servers_due_for_a2s_poll(
    *,
    session: AsyncSession,
    now: datetime,
    plugin_stale_after_seconds: int,
    a2s_poll_after_seconds: int,
) -> list[Server]:
    plugin_cutoff_dt = now - timedelta(seconds=plugin_stale_after_seconds)
    a2s_cutoff_dt = now - timedelta(seconds=a2s_poll_after_seconds)

    statement = select(Server).where(col(Server.enabled).is_(True))
    servers = list((await session.exec(statement)).all())
    await _hydrate_servers(session=session, servers=servers)

    due_servers: list[Server] = []
    for server in servers:
        status = server.live_status
        last_plugin_seen_at = status.last_plugin_seen_at if status else None
        last_a2s_seen_at = status.last_a2s_seen_at if status else None

        if last_plugin_seen_at is not None and last_plugin_seen_at >= plugin_cutoff_dt:
            continue
        if last_a2s_seen_at is not None and last_a2s_seen_at >= a2s_cutoff_dt:
            continue
        due_servers.append(server)

    due_servers.sort(key=lambda server: str(server.id))
    return due_servers


async def read_server_history(
    *,
    session: AsyncSession,
    server_id: uuid.UUID,
    query: ServerHistoryQuery,
) -> list[ServerHistoryBucketPublic]:
    now = get_datetime_utc()
    from_at = query.from_at or datetime.fromtimestamp(now.timestamp() - 3600, tz=UTC)
    to_at = query.to_at or now

    statement = (
        select(ServerHeartbeatRaw)
        .where(col(ServerHeartbeatRaw.server_id) == server_id)
        .where(col(ServerHeartbeatRaw.observed_at) >= from_at)
        .where(col(ServerHeartbeatRaw.observed_at) <= to_at)
        .order_by(col(ServerHeartbeatRaw.observed_at).desc())
    )
    rows = list((await session.exec(statement)).all())

    buckets: OrderedDict[datetime, ServerHistoryBucketPublic] = OrderedDict()
    for row in rows:
        bucket_epoch = math.floor(row.observed_at.timestamp() / query.bucket_seconds)
        bucket_start = datetime.fromtimestamp(
            bucket_epoch * query.bucket_seconds,
            tz=UTC,
        )
        bucket = buckets.get(bucket_start)
        if bucket is None:
            bucket = ServerHistoryBucketPublic(
                bucket_start=bucket_start,
                heartbeat_count=0,
                hostname=row.hostname,
                map=row.map,
                player_count=row.player_count,
                max_players=row.max_players,
                players=row.players,
                is_online=row.is_online,
            )
            buckets[bucket_start] = bucket
        bucket.heartbeat_count += 1

    return list(reversed(list(buckets.values())))


async def _record_server_status(
    *,
    session: AsyncSession,
    server: Server,
    source: ServerHeartbeatSource,
    observed_at: datetime,
    hostname: str,
    map_name: str,
    player_count: int,
    max_players: int,
    players: list[dict[str, Any]],
    is_online: bool,
) -> None:
    status = await _get_server_live_status(session=session, server=server)
    if status is None:
        status = ServerLiveStatus(
            server_id=server.id,
            current_hostname=hostname,
            map=map_name,
            player_count=player_count,
            max_players=max_players,
            players=players,
            is_online=is_online,
            updated_at=observed_at,
        )
        server.live_status = status
    status.updated_at = observed_at

    if source == ServerHeartbeatSource.PLUGIN:
        status.current_hostname = hostname
        status.map = map_name
        status.player_count = player_count
        status.max_players = max_players
        status.players = players
        status.is_online = True
        status.last_plugin_seen_at = observed_at
        status.last_successful_seen_at = observed_at
    else:
        plugin_is_fresh = (
            status.last_plugin_seen_at is not None
            and (observed_at - status.last_plugin_seen_at).total_seconds() <= 5
        )
        status.last_a2s_seen_at = observed_at
        if not plugin_is_fresh:
            status.current_hostname = hostname
            status.map = map_name
            status.player_count = player_count
            status.max_players = max_players
            status.players = players
            status.is_online = is_online
            status.last_successful_seen_at = observed_at

    session.add(status)
    heartbeat = ServerHeartbeatRaw(
        server_id=server.id,
        source=source,
        observed_at=observed_at,
        hostname=hostname,
        map=map_name,
        player_count=player_count,
        max_players=max_players,
        players=players,
        is_online=is_online,
    )
    session.add(heartbeat)


async def _get_server_live_status(
    *,
    session: AsyncSession,
    server: Server,
) -> ServerLiveStatus | None:
    if "live_status" in server.__dict__:
        loaded_status = server.__dict__["live_status"]
        if isinstance(loaded_status, ServerLiveStatus):
            return loaded_status
        return None

    statement = select(ServerLiveStatus).where(
        col(ServerLiveStatus.server_id) == server.id
    )
    status = (await session.exec(statement)).first()
    server.live_status = status
    return status


async def _hydrate_servers(
    *,
    session: AsyncSession,
    servers: list[Server],
) -> None:
    if not servers:
        return

    group_ids = {server.group_id for server in servers if server.group_id is not None}
    server_ids = [server.id for server in servers]

    groups_by_id: dict[uuid.UUID, ServerGroup] = {}
    if group_ids:
        groups_statement = select(ServerGroup).where(col(ServerGroup.id).in_(group_ids))
        groups = list((await session.exec(groups_statement)).all())
        groups_by_id = {group.id: group for group in groups}

    statuses_statement = select(ServerLiveStatus).where(
        col(ServerLiveStatus.server_id).in_(server_ids)
    )
    statuses = list((await session.exec(statuses_statement)).all())
    statuses_by_server_id = {status.server_id: status for status in statuses}

    live_map_names = {
        status.map.strip()
        for status in statuses
        if status.map is not None and status.map.strip()
    }
    map_tiers_by_name: dict[str, int] = {}
    if live_map_names:
        maps_statement = select(Map).where(col(Map.name).in_(live_map_names))
        maps = list((await session.exec(maps_statement)).all())
        map_tiers_by_name = {map_obj.name: map_obj.difficulty for map_obj in maps}

    for server in servers:
        server.group = groups_by_id.get(server.group_id) if server.group_id else None
        server.live_status = statuses_by_server_id.get(server.id)
        live_map_name = (
            server.live_status.map.strip()
            if server.live_status and server.live_status.map
            else None
        )
        server.__dict__["map_tier"] = (
            map_tiers_by_name.get(live_map_name) if live_map_name else None
        )
