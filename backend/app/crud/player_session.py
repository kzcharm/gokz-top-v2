import uuid
from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import String, bindparam, func, text, update
from sqlalchemy import cast as sa_cast
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    AdminPlayerSessionIpLinkBucketPublic,
    AdminPlayerSessionIpLinkMatchMode,
    AdminPlayerSessionIpLinkPlayerPublic,
    AdminPlayerSessionIpLinkPublic,
    AdminPlayerSessionIpLinkSkippedBucketPublic,
    AdminPlayerSessionIpLinksPublic,
    AdminPlayerSessionPublic,
    Player,
    PlayerSession,
    PlayerSessionConnect,
    PlayerSessionDisconnect,
    PlayerSessionHeartbeat,
    PlayerSessionPublic,
    ServerGroup,
    get_datetime_utc,
)
from app.services.geoip import GeoIPLocation, lookup_geoip_city

from .player import to_player_public


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


def to_admin_player_session_public(
    *,
    player_session: PlayerSession,
    player: Player,
    server_group: ServerGroup,
) -> AdminPlayerSessionPublic:
    return AdminPlayerSessionPublic(
        id=player_session.id,
        player=to_player_public(player=player),
        server_group_id=server_group.id,
        server_group_name=server_group.name,
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


async def read_admin_player_sessions(
    *,
    session: AsyncSession,
    offset: int = 0,
    limit: int = 20,
    latest_only: bool = False,
    sort_by: str = "connected_at",
    sort_order: str = "desc",
) -> tuple[list[tuple[PlayerSession, Player, ServerGroup]], int]:
    sort_columns = {
        "connected_at": col(PlayerSession.connected_at),
        "last_heartbeat_at": col(PlayerSession.last_heartbeat_at),
        "disconnect_at": col(PlayerSession.disconnect_at),
        "duration_seconds": col(PlayerSession.duration_seconds),
    }
    sort_column = sort_columns.get(sort_by, col(PlayerSession.connected_at))
    sort_direction = sort_column.asc() if sort_order == "asc" else sort_column.desc()
    session_id_sort = sa_cast(col(PlayerSession.id), String)

    statement = (
        select(PlayerSession, Player, ServerGroup)
        .select_from(PlayerSession)
        .join(Player, col(Player.steamid64) == col(PlayerSession.player_steamid64))
        .join(ServerGroup, col(ServerGroup.id) == col(PlayerSession.server_group_id))
    )

    if latest_only:
        session_rank = (
            func.row_number()
            .over(
                partition_by=col(PlayerSession.player_steamid64),
                order_by=[
                    col(PlayerSession.connected_at).desc(),
                    session_id_sort.desc(),
                ],
            )
            .label("session_rank")
        )
        latest_sessions = select(
            col(PlayerSession.id).label("session_id"),
            session_rank,
        ).subquery()
        statement = statement.join(
            latest_sessions,
            latest_sessions.c.session_id == col(PlayerSession.id),
        ).where(latest_sessions.c.session_rank == 1)
        count_statement = select(func.count()).select_from(
            select(latest_sessions.c.session_id)
            .where(latest_sessions.c.session_rank == 1)
            .subquery()
        )
    else:
        count_statement = select(func.count()).select_from(PlayerSession)

    count = (await session.exec(count_statement)).one()
    rows = cast(
        list[tuple[PlayerSession, Player, ServerGroup]],
        list(
            (
                await session.exec(
                    statement.order_by(
                        sort_direction.nullslast(),
                        col(PlayerSession.connected_at).desc(),
                        session_id_sort.desc(),
                    )
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
        ),
    )
    return rows, count


def _ip_link_bucket_sql(match_mode: AdminPlayerSessionIpLinkMatchMode) -> tuple[str, str]:
    if match_mode == "exact_ip":
        return (
            """
            host(ip_address) AS bucket_key,
            host(ip_address) AS bucket_label,
            host(ip_address) AS bucket_ip_address,
            NULL::text AS bucket_ip_prefix,
            NULL::text AS bucket_geo_country,
            NULL::text AS bucket_geo_region,
            NULL::text AS bucket_geo_city
            """,
            "",
        )
    if match_mode == "same_24":
        return (
            """
            set_masklen(ip_address::cidr, 24)::text AS bucket_key,
            set_masklen(ip_address::cidr, 24)::text AS bucket_label,
            NULL::text AS bucket_ip_address,
            set_masklen(ip_address::cidr, 24)::text AS bucket_ip_prefix,
            NULL::text AS bucket_geo_country,
            NULL::text AS bucket_geo_region,
            NULL::text AS bucket_geo_city
            """,
            "",
        )
    return (
        """
        concat_ws(
            '|',
            set_masklen(ip_address::cidr, 16)::text,
            geo_country,
            geo_region,
            geo_city
        ) AS bucket_key,
        (
            set_masklen(ip_address::cidr, 16)::text
            || ' / '
            || geo_country
            || ' / '
            || geo_region
            || ' / '
            || geo_city
        ) AS bucket_label,
        NULL::text AS bucket_ip_address,
        set_masklen(ip_address::cidr, 16)::text AS bucket_ip_prefix,
        geo_country AS bucket_geo_country,
        geo_region AS bucket_geo_region,
        geo_city AS bucket_geo_city
        """,
        """
        AND geo_country IS NOT NULL
        AND geo_region IS NOT NULL
        AND geo_city IS NOT NULL
        """,
    )


def _player_bucket_cte_sql(match_mode: AdminPlayerSessionIpLinkMatchMode) -> str:
    bucket_sql, extra_where = _ip_link_bucket_sql(match_mode)
    return f"""
    WITH session_buckets AS (
        SELECT
            player_steamid64,
            id AS session_id,
            connected_at,
            {bucket_sql}
        FROM player_session
        WHERE connected_at >= :from_at
          AND connected_at <= :to_at
          {extra_where}
    ),
    player_buckets AS (
        SELECT
            player_steamid64,
            bucket_key,
            bucket_label,
            bucket_ip_address,
            bucket_ip_prefix,
            bucket_geo_country,
            bucket_geo_region,
            bucket_geo_city,
            COUNT(*)::integer AS session_count,
            MIN(connected_at) AS first_seen_at,
            MAX(connected_at) AS last_seen_at
        FROM session_buckets
        GROUP BY
            player_steamid64,
            bucket_key,
            bucket_label,
            bucket_ip_address,
            bucket_ip_prefix,
            bucket_geo_country,
            bucket_geo_region,
            bucket_geo_city
    )
    """


def _bucket_from_row(row: object) -> AdminPlayerSessionIpLinkBucketPublic:
    values = row._mapping  # type: ignore[attr-defined]
    return AdminPlayerSessionIpLinkBucketPublic(
        key=values["bucket_key"],
        label=values["bucket_label"],
        ip_address=values["bucket_ip_address"],
        ip_prefix=values["bucket_ip_prefix"],
        geo_country=values["bucket_geo_country"],
        geo_region=values["bucket_geo_region"],
        geo_city=values["bucket_geo_city"],
    )


async def read_admin_player_session_ip_links(
    *,
    session: AsyncSession,
    steamid64: int,
    match_mode: AdminPlayerSessionIpLinkMatchMode,
    from_at: datetime | None,
    to_at: datetime | None,
    days: int,
    depth: int,
    max_players_per_bucket: int,
) -> AdminPlayerSessionIpLinksPublic | None:
    target = await session.get(Player, steamid64)
    if target is None:
        return None

    resolved_to_at = to_at or get_datetime_utc()
    resolved_from_at = from_at or resolved_to_at - timedelta(days=days)

    visited: set[int] = {steamid64}
    distances: dict[int, int] = {steamid64: 0}
    link_counts: dict[int, int] = {steamid64: 0}
    frontier: set[int] = {steamid64}
    links: list[AdminPlayerSessionIpLinkPublic] = []
    skipped_buckets: list[AdminPlayerSessionIpLinkSkippedBucketPublic] = []
    skipped_bucket_keys: set[str] = set()
    player_bucket_cte = _player_bucket_cte_sql(match_mode)

    for current_depth in range(1, depth + 1):
        if not frontier:
            break

        bucket_statement = text(
            player_bucket_cte
            + """
            SELECT DISTINCT
                bucket_key,
                bucket_label,
                bucket_ip_address,
                bucket_ip_prefix,
                bucket_geo_country,
                bucket_geo_region,
                bucket_geo_city
            FROM player_buckets
            WHERE player_steamid64 IN :frontier_players
            ORDER BY bucket_label
            """
        ).bindparams(bindparam("frontier_players", expanding=True))
        bucket_rows = (
            await session.exec(
                cast(Any, bucket_statement),
                params={
                    "from_at": resolved_from_at,
                    "to_at": resolved_to_at,
                    "frontier_players": list(frontier),
                },
            )
        ).all()
        buckets = {
            row._mapping["bucket_key"]: _bucket_from_row(row)
            for row in bucket_rows
        }
        if not buckets:
            break

        count_statement = text(
            player_bucket_cte
            + """
            SELECT bucket_key, COUNT(*)::integer AS player_count
            FROM player_buckets
            WHERE bucket_key IN :bucket_keys
            GROUP BY bucket_key
            """
        ).bindparams(bindparam("bucket_keys", expanding=True))
        count_rows = (
            await session.exec(
                cast(Any, count_statement),
                params={
                    "from_at": resolved_from_at,
                    "to_at": resolved_to_at,
                    "bucket_keys": list(buckets),
                },
            )
        ).all()
        allowed_bucket_keys: list[str] = []
        for row in count_rows:
            values = row._mapping
            bucket_key = values["bucket_key"]
            player_count = values["player_count"]
            if player_count > max_players_per_bucket:
                if bucket_key not in skipped_bucket_keys:
                    skipped_bucket_keys.add(bucket_key)
                    skipped_buckets.append(
                        AdminPlayerSessionIpLinkSkippedBucketPublic(
                            bucket=buckets[bucket_key],
                            reason="too_many_players",
                            player_count=player_count,
                        )
                    )
                continue
            allowed_bucket_keys.append(bucket_key)

        if not allowed_bucket_keys:
            break

        link_statement = text(
            player_bucket_cte
            + """
            SELECT
                from_bucket.player_steamid64 AS from_steamid64,
                to_bucket.player_steamid64 AS to_steamid64,
                from_bucket.bucket_key,
                from_bucket.bucket_label,
                from_bucket.bucket_ip_address,
                from_bucket.bucket_ip_prefix,
                from_bucket.bucket_geo_country,
                from_bucket.bucket_geo_region,
                from_bucket.bucket_geo_city,
                from_bucket.session_count AS session_count_from,
                to_bucket.session_count AS session_count_to,
                LEAST(
                    from_bucket.first_seen_at,
                    to_bucket.first_seen_at
                ) AS first_seen_at,
                GREATEST(
                    from_bucket.last_seen_at,
                    to_bucket.last_seen_at
                ) AS last_seen_at
            FROM player_buckets AS from_bucket
            JOIN player_buckets AS to_bucket
              ON to_bucket.bucket_key = from_bucket.bucket_key
             AND to_bucket.player_steamid64 <> from_bucket.player_steamid64
            WHERE from_bucket.player_steamid64 IN :frontier_players
              AND from_bucket.bucket_key IN :bucket_keys
            ORDER BY from_bucket.player_steamid64, to_bucket.player_steamid64
            """
        ).bindparams(
            bindparam("frontier_players", expanding=True),
            bindparam("bucket_keys", expanding=True),
        )
        link_rows = (
            await session.exec(
                cast(Any, link_statement),
                params={
                    "from_at": resolved_from_at,
                    "to_at": resolved_to_at,
                    "frontier_players": list(frontier),
                    "bucket_keys": allowed_bucket_keys,
                },
            )
        ).all()

        next_frontier: set[int] = set()
        for row in link_rows:
            values = row._mapping
            to_steamid64 = values["to_steamid64"]
            if to_steamid64 in visited:
                continue

            from_steamid64 = values["from_steamid64"]
            next_frontier.add(to_steamid64)
            distances.setdefault(to_steamid64, current_depth)
            link_counts[from_steamid64] = link_counts.get(from_steamid64, 0) + 1
            link_counts[to_steamid64] = link_counts.get(to_steamid64, 0) + 1
            links.append(
                AdminPlayerSessionIpLinkPublic(
                    from_steamid64=str(from_steamid64),
                    to_steamid64=str(to_steamid64),
                    distance=current_depth,
                    bucket=_bucket_from_row(row),
                    match_mode=match_mode,
                    session_count_from=values["session_count_from"],
                    session_count_to=values["session_count_to"],
                    first_seen_at=values["first_seen_at"],
                    last_seen_at=values["last_seen_at"],
                )
            )

        visited.update(next_frontier)
        frontier = next_frontier

    player_rows = (
        await session.exec(
            select(Player).where(col(Player.steamid64).in_(list(distances)))
        )
    ).all()
    players_by_steamid64 = {player.steamid64: player for player in player_rows}
    players = [
        AdminPlayerSessionIpLinkPlayerPublic(
            player=to_player_public(player=players_by_steamid64[player_steamid64]),
            distance=distances[player_steamid64],
            link_count=link_counts.get(player_steamid64, 0),
        )
        for player_steamid64 in sorted(
            distances,
            key=lambda value: (distances[value], str(value)),
        )
        if player_steamid64 in players_by_steamid64
    ]

    return AdminPlayerSessionIpLinksPublic(
        target=to_player_public(player=target),
        match_mode=match_mode,
        depth=depth,
        from_at=resolved_from_at,
        to_at=resolved_to_at,
        players=players,
        links=links,
        skipped_buckets=skipped_buckets,
    )


async def _ensure_player_for_session(
    *,
    session: AsyncSession,
    steamid64: int,
    now: datetime,
    location: GeoIPLocation | None,
) -> None:
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

    location = lookup_geoip_city(str(payload.ip_address))
    await _ensure_player_for_session(
        session=session,
        steamid64=player_steamid64,
        now=payload.connected_at,
        location=location,
    )
    player_session = PlayerSession(
        id=payload.session_id,
        player_steamid64=player_steamid64,
        server_group_id=group.id,
        connected_at=payload.connected_at,
        last_heartbeat_at=payload.connected_at,
        ip_address=str(payload.ip_address),
        geo_country=location.country_code if location is not None else None,
        geo_region=location.region_name if location is not None else None,
        geo_city=location.city_name if location is not None else None,
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
    "read_admin_player_session_ip_links",
    "read_admin_player_sessions",
    "to_admin_player_session_public",
    "to_player_session_public",
]
