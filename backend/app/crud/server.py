from __future__ import annotations

import math
import uuid
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, or_, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.regions import get_region_code_for_country, get_region_country_codes
from app.models import (
    AdminServerGroupPublic,
    Map,
    MapReview,
    PlayerSession,
    Server,
    ServerCreate,
    ServerGlobalapi,
    ServerGlobalStatusPublic,
    ServerGlobalStatusPut,
    ServerGroup,
    ServerGroupCreate,
    ServerGroupDependencyCounts,
    ServerGroupPublic,
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
    ServerLiveStatusStatePublic,
    ServerPlayerPublic,
    ServerPublic,
    ServerSource,
    ServerStatus,
    ServerStatusPut,
    ServerUpdate,
    get_datetime_utc,
)
from app.services.ip_location import lookup_ip_location

SERVER_STATUS_NOTIFY_CHANNEL = "server_status_updates"
SERVER_A2S_FAILURES_BEFORE_OFFLINE = 3
SERVER_INVALID_AFTER = timedelta(hours=1)
SERVER_INVALID_COUNT_THRESHOLD = 10
SERVER_OFFLINE_INVALID_AFTER = timedelta(hours=24)
SERVER_TIMEOUT_INVALID_COUNT_THRESHOLD = 100


def _normalize_server_location_value(value: str | None) -> str | None:
    if value is None:
        return None
    normalized_value = value.strip()
    return normalized_value or None


async def _resolve_server_location(
    *,
    ip: str,
    country: str | None,
    city: str | None,
    latitude: float | None,
    longitude: float | None,
) -> tuple[str | None, str | None, float | None, float | None]:
    normalized_country = _normalize_server_location_value(country)
    normalized_city = _normalize_server_location_value(city)
    resolved_latitude = latitude
    resolved_longitude = longitude
    if (
        normalized_country is not None
        and normalized_city is not None
        and resolved_latitude is not None
        and resolved_longitude is not None
    ):
        return normalized_country, normalized_city, resolved_latitude, resolved_longitude

    location = await lookup_ip_location(ip)
    if location is None:
        return normalized_country, normalized_city, resolved_latitude, resolved_longitude

    return (
        normalized_country or location.country_code,
        normalized_city or location.city_name,
        resolved_latitude if resolved_latitude is not None else location.latitude,
        resolved_longitude if resolved_longitude is not None else location.longitude,
    )


async def _refresh_server_location(
    *,
    server: Server,
    ip: str | None = None,
    force: bool = False,
) -> None:
    lookup_ip = ip or server.ip
    if (
        not force
        and server.country is not None
        and server.city is not None
        and server.latitude is not None
        and server.longitude is not None
    ):
        return

    server.country, server.city, server.latitude, server.longitude = (
        await _resolve_server_location(
            ip=lookup_ip,
            country=server.country,
            city=server.city,
            latitude=server.latitude,
            longitude=server.longitude,
        )
    )


def normalize_server_map_name(map_name: str | None) -> str | None:
    if map_name is None:
        return None
    normalized_parts = [
        part.strip()
        for part in map_name.strip().replace("\\", "/").split("/")
        if part.strip()
    ]
    if not normalized_parts:
        return None
    return normalized_parts[-1]


def parse_server_workshop_id(map_name: str | None) -> str | None:
    if map_name is None:
        return None
    normalized_parts = [
        part.strip()
        for part in map_name.strip().replace("\\", "/").split("/")
        if part.strip()
    ]
    if (
        len(normalized_parts) >= 3
        and normalized_parts[0].casefold() == "workshop"
        and normalized_parts[1].isdigit()
    ):
        return normalized_parts[1]
    return None


def _build_server_live_status_public(
    status: ServerLiveStatus | None,
    workshop_id: int | str | None = None,
) -> ServerLiveStatusPublic | None:
    if status is None:
        return None
    state = _get_live_status_state(status)
    global_status = _build_server_global_status_public(status.global_status)
    parsed_workshop_id = parse_server_workshop_id(status.map)
    return ServerLiveStatusPublic(
        hostname=status.hostname,
        map=normalize_server_map_name(status.map),
        workshop_id=parsed_workshop_id or (str(workshop_id) if workshop_id else None),
        player_count=status.player_count,
        max_players=status.max_players,
        players=_build_server_player_public_list(status.players),
        is_online=status.is_online,
        global_status=global_status,
        state=state,
        updated_at=status.updated_at,
    )


SUPPORTED_GLOBAL_MODES = ("KZT", "SKZ", "VNL")


def _build_server_global_status_public(
    raw_status: dict[str, Any] | None,
) -> ServerGlobalStatusPublic | None:
    if not isinstance(raw_status, dict):
        return None
    try:
        status = ServerGlobalStatusPut.model_validate(raw_status)
    except ValidationError:
        return None
    modes = {
        mode: bool(status.modes.get(mode, False))
        for mode in SUPPORTED_GLOBAL_MODES
    }
    public_data = status.model_dump()
    public_data["modes"] = modes
    return ServerGlobalStatusPublic(
        **public_data,
        eligible=(
            status.api_key_valid
            and status.plugins_valid
            and status.settings_enforcer_valid
            and status.map_valid
            and any(modes.values())
        ),
    )


def _build_server_player_public_list(
    raw_players: list[dict[str, Any]] | Any,
) -> list[ServerPlayerPublic]:
    if not isinstance(raw_players, list):
        return []

    players: list[ServerPlayerPublic] = []
    for raw_player in raw_players:
        if not isinstance(raw_player, dict):
            continue
        try:
            players.append(ServerPlayerPublic.model_validate(raw_player))
        except ValidationError:
            continue
    return players


def _get_live_status_state(status: ServerLiveStatus) -> ServerLiveStatusStatePublic:
    raw_state = status.state if isinstance(status.state, dict) else {}
    return ServerLiveStatusStatePublic.model_validate(raw_state)


def _set_live_status_state(
    status: ServerLiveStatus,
    state: ServerLiveStatusStatePublic,
) -> None:
    status.state = state.model_dump(mode="json")


def _evaluate_server_status(
    *,
    current_status: ServerStatus,
    live_status: ServerLiveStatus,
    observed_at: datetime,
) -> ServerStatus:
    if current_status == ServerStatus.DISABLED:
        return current_status

    state = _get_live_status_state(live_status)
    if live_status.is_online:
        if server_status_is_valid(map_name=live_status.map or ""):
            return ServerStatus.ENABLED
        if (
            state.last_valid_seen_at is not None
            and observed_at - state.last_valid_seen_at > SERVER_INVALID_AFTER
            and state.invalid_count > SERVER_INVALID_COUNT_THRESHOLD
        ):
            return ServerStatus.INVALID
        return ServerStatus.ENABLED

    if (
        state.last_successful_seen_at is not None
        and observed_at - state.last_successful_seen_at >= SERVER_OFFLINE_INVALID_AFTER
        and state.timeout_count >= SERVER_TIMEOUT_INVALID_COUNT_THRESHOLD
    ):
        return ServerStatus.INVALID
    return ServerStatus.ENABLED


def to_server_public(*, server: Server) -> ServerPublic:
    group = None
    loaded_group = server.__dict__.get("group")
    if isinstance(loaded_group, ServerGroup):
        group = ServerGroupSummary(
            id=loaded_group.id,
            name=loaded_group.name,
            custom_id=loaded_group.custom_id,
        )

    loaded_status = server.__dict__.get("live_status")

    return ServerPublic(
        id=server.id,
        group_id=server.group_id,
        group=group,
        ip=server.ip,
        port=server.port,
        status=server.status,
        country=server.country,
        city=server.city,
        region=get_region_code_for_country(server.country),
        latitude=server.latitude,
        longitude=server.longitude,
        source=server.source,
        last_discovered_at=server.last_discovered_at,
        map_tier=server.__dict__.get("map_tier"),
        created_at=server.created_at,
        updated_at=server.updated_at,
        live_status=(
            _build_server_live_status_public(
                loaded_status,
                workshop_id=server.__dict__.get("map_workshop_id"),
            )
            if isinstance(loaded_status, ServerLiveStatus)
            else None
        ),
    )


def to_server_group_public(
    *,
    group: ServerGroup,
    server_count: int = 0,
) -> ServerGroupPublic:
    return ServerGroupPublic(
        id=group.id,
        name=group.name,
        custom_id=group.custom_id,
        website=group.website,
        discord=group.discord,
        steam_group=group.steam_group,
        owner_steamid64=(
            str(group.owner_steamid64) if group.owner_steamid64 is not None else None
        ),
        status=group.status,
        server_count=server_count,
        last_api_key_used_at=group.last_api_key_used_at,
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


def to_admin_server_group_public(
    *,
    group: ServerGroup,
    server_count: int = 0,
) -> AdminServerGroupPublic:
    public_group = to_server_group_public(group=group, server_count=server_count)
    return AdminServerGroupPublic(
        **public_group.model_dump(),
        api_key=group.api_key,
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
        and server.status == ServerStatus.ENABLED
        and server.group_id == group.id
    )


def build_manual_server_source(*, steamid64: int | str) -> dict[str, str]:
    return {
        "type": ServerSource.MANUAL.value,
        "steamid64": str(steamid64),
    }


def build_plugin_server_source(*, group: ServerGroup) -> dict[str, str]:
    source: dict[str, str] = {
        "type": ServerSource.MANUAL.value,
        "origin": "plugin",
        "server_group_id": str(group.id),
    }
    if group.owner_steamid64 is not None:
        source["steamid64"] = str(group.owner_steamid64)
    return source


def build_steam_master_server_source() -> dict[str, str]:
    return {"type": ServerSource.STEAM_MASTER.value}


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


def mark_server_group_api_key_used(*, session: AsyncSession, group: ServerGroup) -> None:
    group.last_api_key_used_at = get_datetime_utc()
    session.add(group)


async def get_server_groups_by_custom_id_or_name(
    *,
    session: AsyncSession,
    identifier: str,
) -> list[ServerGroup]:
    statement = select(ServerGroup).where(
        or_(
            col(ServerGroup.custom_id) == identifier,
            col(ServerGroup.name) == identifier,
        )
    )
    return list((await session.exec(statement)).all())


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


async def read_server_groups_for_admin(
    *,
    session: AsyncSession,
    owner_steamid64: int | None = None,
) -> tuple[list[ServerGroup], dict[uuid.UUID, int]]:
    groups_statement = select(ServerGroup)
    if owner_steamid64 is not None:
        groups_statement = groups_statement.where(
            col(ServerGroup.owner_steamid64) == owner_steamid64
        )
    groups_statement = groups_statement.order_by(col(ServerGroup.name).asc())
    groups = list((await session.exec(groups_statement)).all())
    group_ids = {group.id for group in groups}
    if not group_ids:
        return groups, {}

    servers_statement = (
        select(Server.group_id, func.count())
        .where(col(Server.group_id).in_(group_ids))
        .group_by(col(Server.group_id))
    )
    return groups, {
        group_id: count
        for group_id, count in (await session.exec(servers_statement)).all()
        if group_id is not None
    }


async def get_server_group_dependency_counts(
    *,
    session: AsyncSession,
    group_id: uuid.UUID,
) -> ServerGroupDependencyCounts:
    server_count = (
        await session.exec(
            select(func.count()).select_from(Server).where(Server.group_id == group_id)
        )
    ).one()
    globalapi_count = (
        await session.exec(
            select(func.count())
            .select_from(ServerGlobalapi)
            .where(ServerGlobalapi.group_id == group_id)
        )
    ).one()
    map_review_count = (
        await session.exec(
            select(func.count())
            .select_from(MapReview)
            .where(MapReview.server_group_id == group_id)
        )
    ).one()
    player_session_count = (
        await session.exec(
            select(func.count())
            .select_from(PlayerSession)
            .where(PlayerSession.server_group_id == group_id)
        )
    ).one()
    return ServerGroupDependencyCounts(
        servers=server_count,
        globalapi_servers=globalapi_count,
        map_reviews=map_review_count,
        player_sessions=player_session_count,
    )


async def create_server_group(
    *,
    session: AsyncSession,
    group_in: ServerGroupCreate,
    owner_steamid64: int,
    initial_status: ServerGroupStatus = ServerGroupStatus.PENDING,
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
        custom_id=group_in.custom_id,
        website=group_in.website,
        discord=group_in.discord,
        steam_group=group_in.steam_group,
        api_key=api_key,
        owner_steamid64=owner_steamid64,
        status=initial_status,
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
            if server.status == ServerStatus.DISABLED:
                continue
            server.status = ServerStatus.DISABLED
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
    counts = await get_server_group_dependency_counts(
        session=session, group_id=group.id
    )
    if counts.total > 0:
        raise ValueError("Server group has dependencies")
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
    owned_group_ids: set[uuid.UUID] | frozenset[uuid.UUID] | None = None,
) -> tuple[list[Server], int]:
    statement = select(Server)
    if query.q:
        search = f"%{query.q.strip()}%"
        statement = statement.outerjoin(
            ServerLiveStatus,
            col(ServerLiveStatus.server_id) == col(Server.id),
        ).where(
            or_(
                col(Server.ip).ilike(search),
                col(Server.city).ilike(search),
                col(ServerLiveStatus.hostname).ilike(search),
            )
        )
    if owned_group_ids is not None:
        if not owned_group_ids:
            return [], 0
        statement = statement.where(col(Server.group_id).in_(owned_group_ids))
    if query.group_id is not None:
        if owned_group_ids is not None and query.group_id not in owned_group_ids:
            return [], 0
        statement = statement.where(col(Server.group_id) == query.group_id)
    if query.ungrouped:
        statement = statement.where(col(Server.group_id).is_(None))
    if query.status is not None:
        statement = statement.where(col(Server.status) == query.status)
    if query.country:
        statement = statement.where(col(Server.country) == query.country.upper())
    if query.region:
        region_country_codes = get_region_country_codes(query.region)
        if region_country_codes is not None:
            statement = statement.where(
                col(Server.country).in_(list(region_country_codes))
            )
        else:
            return [], 0
    if query.city:
        statement = statement.where(col(Server.city) == query.city)
    if query.source_type is not None:
        statement = statement.where(
            Server.source["type"].astext == query.source_type.value
        )
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
            (server.live_status.hostname if server.live_status else None) or "",
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
    steamid64: int,
    queried_hostname: str,
    queried_map: str,
    queried_player_count: int,
    queried_max_players: int,
    queried_players: list[dict[str, Any]],
    notify: bool = True,
) -> Server:
    await _validate_group_id(session=session, group_id=server_in.group_id)

    existing_server = await get_server_by_endpoint(
        session=session,
        ip=server_in.ip,
        port=server_in.port,
        hydrate=False,
    )
    if existing_server is not None:
        if existing_server.status == ServerStatus.DISABLED:
            raise ValueError("Server is disabled")
        if existing_server.status == ServerStatus.ENABLED:
            raise ValueError("Server already exists")

        now = get_datetime_utc()
        resolved_country, resolved_city, resolved_latitude, resolved_longitude = (
            await _resolve_server_location(
                ip=server_in.ip,
                country=server_in.country,
                city=server_in.city,
                latitude=server_in.latitude,
                longitude=server_in.longitude,
            )
        )
        existing_server.group_id = server_in.group_id
        existing_server.status = server_in.status
        existing_server.country = resolved_country
        existing_server.city = resolved_city
        existing_server.latitude = resolved_latitude
        existing_server.longitude = resolved_longitude
        existing_server.source = build_manual_server_source(steamid64=steamid64)
        existing_server.updated_at = now
        session.add(existing_server)

        await _record_server_status(
            session=session,
            server=existing_server,
            source=ServerHeartbeatSource.A2S,
            observed_at=now,
            hostname=queried_hostname,
            map_name=queried_map,
            player_count=queried_player_count,
            max_players=queried_max_players,
            players=queried_players,
            is_online=True,
        )
        existing_server.status = ServerStatus.ENABLED
        if notify:
            await notify_server_status_updated(
                session=session,
                server_id=existing_server.id,
            )
        await session.commit()
        await session.refresh(existing_server)
        return (
            await get_server_by_id(session=session, server_id=existing_server.id)
            or existing_server
        )

    now = get_datetime_utc()
    resolved_country, resolved_city, resolved_latitude, resolved_longitude = (
        await _resolve_server_location(
            ip=server_in.ip,
            country=server_in.country,
            city=server_in.city,
            latitude=server_in.latitude,
            longitude=server_in.longitude,
        )
    )
    server = Server(
        group_id=server_in.group_id,
        ip=server_in.ip,
        port=server_in.port,
        status=server_in.status,
        country=resolved_country,
        city=resolved_city,
        latitude=resolved_latitude,
        longitude=resolved_longitude,
        source=build_manual_server_source(steamid64=steamid64),
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
    if notify:
        await notify_server_status_updated(session=session, server_id=server.id)
    await session.commit()
    await session.refresh(server)
    return await get_server_by_id(session=session, server_id=server.id) or server


async def upsert_server_from_plugin_heartbeat(
    *,
    session: AsyncSession,
    group: ServerGroup,
    payload: ServerStatusPut,
) -> Server:
    server = await get_server_by_endpoint(
        session=session,
        ip=payload.ip,
        port=payload.port,
    )
    now = get_datetime_utc()

    if server is None:
        resolved_country, resolved_city, resolved_latitude, resolved_longitude = (
            await _resolve_server_location(
                ip=payload.ip,
                country=None,
                city=None,
                latitude=None,
                longitude=None,
            )
        )
        server = Server(
            group_id=group.id,
            ip=payload.ip,
            port=payload.port,
            status=ServerStatus.ENABLED,
            country=resolved_country,
            city=resolved_city,
            latitude=resolved_latitude,
            longitude=resolved_longitude,
            source=build_plugin_server_source(group=group),
            created_at=now,
            updated_at=now,
        )
        session.add(server)
        try:
            await session.flush()
        except IntegrityError as exc:
            await session.rollback()
            server = await get_server_by_endpoint(
                session=session,
                ip=payload.ip,
                port=payload.port,
            )
            if server is None:
                raise ValueError("Server already exists") from exc

            if server.group_id is not None and server.group_id != group.id:
                raise ValueError("Server does not belong to this server group") from exc

            server.group_id = group.id
            server.status = ServerStatus.ENABLED
            await _refresh_server_location(server=server, ip=payload.ip)
            server.source = build_plugin_server_source(group=group)
            server.updated_at = now
            session.add(server)
    else:
        if server.group_id is not None and server.group_id != group.id:
            raise ValueError("Server does not belong to this server group")

        server.group_id = group.id
        server.status = ServerStatus.ENABLED
        await _refresh_server_location(server=server, ip=payload.ip)
        server.source = build_plugin_server_source(group=group)
        server.updated_at = now
        session.add(server)

    return await record_plugin_heartbeat(
        session=session,
        group=group,
        server=server,
        payload=payload,
    )


async def update_server(
    *,
    session: AsyncSession,
    server: Server,
    server_in: ServerUpdate,
) -> Server:
    update_data = server_in.model_dump(exclude_unset=True)
    if "group_id" in update_data:
        await _validate_group_id(session=session, group_id=update_data["group_id"])
    previous_ip = server.ip
    location_fields = {"country", "city", "latitude", "longitude"}
    server.sqlmodel_update(update_data)
    ip_changed = "ip" in update_data and server.ip != previous_ip
    if ip_changed:
        for field_name in location_fields - update_data.keys():
            setattr(server, field_name, None)
    await _refresh_server_location(server=server, force=ip_changed)
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
    notify: bool = True,
) -> Server:
    server = await get_server_by_endpoint(
        session=session,
        ip=ip,
        port=port,
        hydrate=False,
    )
    now = observed_at
    if server is None:
        resolved_country, resolved_city, resolved_latitude, resolved_longitude = (
            await _resolve_server_location(
                ip=ip,
                country=None,
                city=None,
                latitude=None,
                longitude=None,
            )
        )
        server = Server(
            ip=ip,
            port=port,
            status=ServerStatus.ENABLED,
            country=resolved_country,
            city=resolved_city,
            latitude=resolved_latitude,
            longitude=resolved_longitude,
            source=build_steam_master_server_source(),
            last_discovered_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(server)
        await session.flush()
    else:
        if server.status != ServerStatus.DISABLED:
            server.status = ServerStatus.ENABLED
        if server.source.get("type") == ServerSource.STEAM_MASTER.value:
            server.source = build_steam_master_server_source()
        await _refresh_server_location(server=server, ip=ip)
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
    if notify:
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
    notify: bool = True,
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
        players=[player.model_dump(mode="json") for player in payload.players],
        is_online=True,
        global_status=(
            payload.global_status.model_dump(mode="json")
            if payload.global_status is not None
            else None
        ),
    )
    if (
        _should_auto_validate_server_group(group=group, server=server)
        and group is not None
    ):
        group.status = ServerGroupStatus.VALIDATED
        group.updated_at = payload.observed_at
        session.add(group)
    if notify:
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
    notify: bool = True,
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
    if notify:
        await notify_server_status_updated(session=session, server_id=server.id)
    await session.commit()
    return await get_server_by_id(session=session, server_id=server.id) or server


async def record_a2s_failure(
    *,
    session: AsyncSession,
    server: Server,
    observed_at: datetime,
    offline_after_failures: int = SERVER_A2S_FAILURES_BEFORE_OFFLINE,
    notify: bool = True,
) -> Server:
    status = await _get_server_live_status(session=session, server=server)
    if status is None:
        status = ServerLiveStatus(server_id=server.id)
        session.add(status)
        server.live_status = status

    state = _get_live_status_state(status)
    state.last_a2s_seen_at = observed_at
    state.timeout_count += 1
    _set_live_status_state(status, state)
    session.add(status)
    mark_offline = state.timeout_count >= offline_after_failures

    if not status.is_online:
        next_status = _evaluate_server_status(
            current_status=server.status,
            live_status=status,
            observed_at=observed_at,
        )
        if server.status != next_status:
            server.status = next_status
        server.updated_at = observed_at
        session.add(server)
        if notify:
            await notify_server_status_updated(session=session, server_id=server.id)
        await session.commit()
        return await get_server_by_id(session=session, server_id=server.id) or server

    if mark_offline:
        status.player_count = 0
        status.players = []
        status.is_online = False
        status.updated_at = observed_at
        session.add(status)

    next_status = _evaluate_server_status(
        current_status=server.status,
        live_status=status,
        observed_at=observed_at,
    )
    if server.status != ServerStatus.DISABLED:
        server.status = next_status
        server.updated_at = observed_at
        session.add(server)
    if notify:
        await notify_server_status_updated(session=session, server_id=server.id)
    await session.commit()
    return await get_server_by_id(session=session, server_id=server.id) or server


async def record_offline_mark(
    *,
    session: AsyncSession,
    server: Server,
    observed_at: datetime,
    notify: bool = True,
) -> Server:
    status = await _get_server_live_status(session=session, server=server)
    if status is None:
        status = ServerLiveStatus(server_id=server.id)
        session.add(status)
        server.live_status = status

    state = _get_live_status_state(status)
    state.last_a2s_seen_at = observed_at
    state.timeout_count += 1
    _set_live_status_state(status, state)
    status.player_count = 0
    status.players = []
    status.is_online = False
    status.updated_at = observed_at
    session.add(status)
    if server.status != ServerStatus.DISABLED:
        server.status = _evaluate_server_status(
            current_status=server.status,
            live_status=status,
            observed_at=observed_at,
        )
        server.updated_at = observed_at
        session.add(server)

    if notify:
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

    statement = select(Server).where(
        col(Server.status).in_([ServerStatus.ENABLED, ServerStatus.INVALID])
    )
    servers = list((await session.exec(statement)).all())
    await _hydrate_servers(session=session, servers=servers)

    due_servers: list[Server] = []
    for server in servers:
        status = server.live_status
        state = _get_live_status_state(status) if status is not None else None
        last_plugin_seen_at = state.last_plugin_seen_at if state else None
        last_a2s_seen_at = state.last_a2s_seen_at if state else None

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
                players=_build_server_player_public_list(row.players),
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
    global_status: dict[str, Any] | None = None,
) -> None:
    status = await _get_server_live_status(session=session, server=server)
    effective_map_name = map_name
    if status is None:
        status = ServerLiveStatus(
            server_id=server.id,
            hostname=hostname,
            map=map_name,
            player_count=player_count,
            max_players=max_players,
            players=players,
            is_online=is_online,
            global_status=global_status,
            state=ServerLiveStatusStatePublic().model_dump(mode="json"),
            updated_at=observed_at,
        )
        server.live_status = status
    status.updated_at = observed_at
    state = _get_live_status_state(status)

    if source == ServerHeartbeatSource.PLUGIN:
        status.hostname = hostname
        status.map = map_name
        status.player_count = player_count
        status.max_players = max_players
        status.players = players
        status.is_online = True
        if global_status is not None:
            status.global_status = global_status
        state.last_plugin_seen_at = observed_at
        state.last_successful_seen_at = observed_at
    else:
        plugin_is_fresh = (
            state.last_plugin_seen_at is not None
            and (observed_at - state.last_plugin_seen_at).total_seconds() <= 5
        )
        state.last_a2s_seen_at = observed_at
        if not plugin_is_fresh:
            status.hostname = hostname
            status.map = map_name
            status.player_count = player_count
            status.max_players = max_players
            status.players = players
            status.is_online = is_online
            state.last_successful_seen_at = observed_at
        else:
            effective_map_name = status.map or map_name

    if status.is_online:
        state.timeout_count = 0
        if server_status_is_valid(map_name=effective_map_name):
            state.last_valid_seen_at = observed_at
            state.invalid_count = 0
        else:
            state.invalid_count += 1
    else:
        state.timeout_count += 1

    _set_live_status_state(status, state)

    if server.status != ServerStatus.DISABLED:
        server.status = _evaluate_server_status(
            current_status=server.status,
            live_status=status,
            observed_at=observed_at,
        )
        server.updated_at = observed_at
        session.add(server)

    session.add(status)
    # Temporary simplification: live status updates no longer persist raw
    # heartbeat history while the historical pipeline is being rewritten.


def server_status_is_valid(*, map_name: str) -> bool:
    normalized_map_name = (normalize_server_map_name(map_name) or "").casefold()
    return normalized_map_name.startswith(
        ("kz_", "bkz_", "vnl_", "skz_", "xc_", "kzpro_")
    )


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
        normalized_map_name
        for status in statuses
        if (normalized_map_name := normalize_server_map_name(status.map)) is not None
    }
    maps_by_name: dict[str, Map] = {}
    if live_map_names:
        maps_statement = select(Map).where(col(Map.name).in_(live_map_names))
        maps = list((await session.exec(maps_statement)).all())
        maps_by_name = {map_obj.name: map_obj for map_obj in maps}

    for server in servers:
        server.group = groups_by_id.get(server.group_id) if server.group_id else None
        server.live_status = statuses_by_server_id.get(server.id)
        live_map_name = normalize_server_map_name(
            server.live_status.map if server.live_status else None
        )
        map_obj = maps_by_name.get(live_map_name) if live_map_name else None
        server.__dict__["map_tier"] = map_obj.difficulty if map_obj else None
        server.__dict__["map_workshop_id"] = map_obj.workshop_id if map_obj else None
