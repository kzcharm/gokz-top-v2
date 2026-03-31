import uuid
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from sqlalchemy import case, text
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    Map,
    Mode,
    Player,
    RecentRecordCompatPublicV0,
    RecentRecordListQuery,
    RecentRecordMapPublic,
    RecentRecordModePublic,
    RecentRecordPlayerPublic,
    RecentRecordPublic,
    RecentRecordServerPublic,
    Record,
    RecordCompatPublicV0,
    RecordListQuery,
    RecordPatch,
    RecordPublic,
    ServerGlobalapi,
    ServerGlobalapiCompatPublicV0,
    TeleportsType,
    WorldRecordCountCompatPublicV0,
    generate_uuid7,
    get_datetime_utc,
)

RECENT_RECORD_NOTIFY_CHANNEL = "recent_record_updates"
RECENT_RECORD_EXACT_COUNT_THRESHOLD = 100_000


def _record_tie_breakers() -> tuple:
    return (
        col(Record.id).asc().nullslast(),
        col(Record.uuid).asc(),
    )


def _parse_pg_stats_boolean_frequency(
    *,
    most_common_vals: str | None,
    most_common_freqs: Sequence[float] | None,
    value: bool,
) -> float | None:
    if not most_common_vals or not most_common_freqs:
        return None

    normalized_values = [
        item.strip() for item in most_common_vals.strip("{}").split(",") if item.strip()
    ]
    target_value = "t" if value else "f"
    for index, current_value in enumerate(normalized_values):
        if current_value != target_value or index >= len(most_common_freqs):
            continue
        return float(most_common_freqs[index])

    return None


async def _estimate_record_count(
    *,
    session: AsyncSession,
    is_valid: bool | None = None,
) -> int:
    total_estimate = (
        await session.exec(
            text("SELECT COALESCE(reltuples, 0) FROM pg_class WHERE oid = 'record'::regclass")
        )
    ).one()
    normalized_total_estimate = max(int(round(float(total_estimate[0]))), 0)

    # Exact counts dominate latency once the table reaches tens of millions of rows.
    # Keep exact results for smaller datasets and tests, then fall back to planner
    # statistics when the table is large.
    if normalized_total_estimate < RECENT_RECORD_EXACT_COUNT_THRESHOLD:
        count_statement = select(func.count()).select_from(Record)
        if is_valid is not None:
            count_statement = count_statement.where(col(Record.is_valid).is_(is_valid))
        return (await session.exec(count_statement)).one()

    if is_valid is None:
        return normalized_total_estimate

    row = (
        await session.exec(
            text(
                """
                SELECT most_common_vals, most_common_freqs
                FROM pg_stats
                WHERE schemaname = 'public'
                  AND tablename = 'record'
                  AND attname = 'is_valid'
                """
            )
        )
    ).one_or_none()
    if row is None:
        return normalized_total_estimate

    selectivity = _parse_pg_stats_boolean_frequency(
        most_common_vals=row[0],
        most_common_freqs=row[1],
        value=is_valid,
    )
    if selectivity is None:
        return normalized_total_estimate

    return max(int(round(normalized_total_estimate * selectivity)), 0)


async def _load_record_context(
    *,
    session: AsyncSession,
    record: Record,
) -> tuple[Player, ServerGlobalapi, Map, Mode]:
    player = await session.get(Player, record.steamid64)
    server = await session.get(ServerGlobalapi, record.server_id)
    map_obj = await session.get(Map, record.map_id)
    mode = await session.get(Mode, record.mode_id)
    if player is None or server is None or map_obj is None or mode is None:
        raise ValueError("Record references missing related entities")
    return player, server, map_obj, mode


def _to_server_globalapi_compat_public_v0(
    *,
    server: ServerGlobalapi,
) -> ServerGlobalapiCompatPublicV0:
    return ServerGlobalapiCompatPublicV0(
        id=server.id,
        port=server.port,
        ip=server.ip,
        name=server.name,
        owner_steamid64=str(server.owner_steamid64),
    )


def to_record_public(
    *,
    record: Record,
    player: Player,
    server: ServerGlobalapi,
    map_obj: Map,
    mode: Mode,
) -> RecordPublic:
    return RecordPublic(
        uuid=record.uuid,
        id=record.id,
        steamid64=str(record.steamid64),
        player_name=player.name,
        player_avatar_hash=player.avatar_hash,
        steam_id=None,
        server_id=record.server_id,
        server_name=server.name or "",
        map_id=record.map_id,
        map_name=map_obj.name,
        mode_id=record.mode_id,
        mode=mode.name,
        stage=record.stage,
        tickrate=128,
        time=float(record.time),
        teleports=record.teleports,
        points=record.points,
        created_on=record.created_on,
        updated_on=record.updated_on,
        updated_by=str(record.updated_by),
        replay_id=record.replay_id,
        is_valid=record.is_valid,
    )


def to_recent_record_public(
    *,
    record: Record,
    player: Player,
    server: ServerGlobalapi,
    map_obj: Map,
    mode: Mode,
) -> RecentRecordPublic:
    return RecentRecordPublic(
        uuid=record.uuid,
        id=record.id,
        player=RecentRecordPlayerPublic(
            steamid64=str(player.steamid64),
            name=player.name,
            alias=player.alias,
            avatar_hash=player.avatar_hash,
            country=player.country,
        ),
        map=RecentRecordMapPublic(
            id=map_obj.id,
            name=map_obj.name,
            tier=map_obj.difficulty,
        ),
        server=RecentRecordServerPublic(
            id=server.id,
            name=server.name or "",
        ),
        mode=RecentRecordModePublic(
            id=mode.id,
            name=mode.name,
        ),
        stage=record.stage,
        teleports=record.teleports,
        time=float(record.time),
        points=record.points,
        created_on=record.created_on,
        updated_on=record.updated_on,
    )


def to_record_compat_public_v0(
    *,
    record: Record,
    player: Player,
    server: ServerGlobalapi,
    map_obj: Map,
    mode: Mode,
) -> RecordCompatPublicV0:
    if record.id is None:
        raise ValueError("Compat responses require a non-null GlobalAPI id")
    return RecordCompatPublicV0(
        id=record.id,
        steamid64=record.steamid64,
        player_name=player.name,
        steam_id=None,
        server_id=record.server_id,
        server_name=server.name or "",
        map_id=record.map_id,
        map_name=map_obj.name,
        mode=mode.name,
        stage=record.stage,
        tickrate=128,
        time=float(record.time),
        teleports=record.teleports,
        points=record.points,
        created_on=record.created_on,
        updated_on=record.updated_on,
        updated_by=record.updated_by,
        record_filter_id=0,
        replay_id=record.replay_id,
        server=_to_server_globalapi_compat_public_v0(server=server),
    )


async def read_records(
    *,
    session: AsyncSession,
    query: RecordListQuery,
) -> tuple[list[Record], int]:
    filters: list[object] = []

    if query.id:
        filters.append(col(Record.id).in_(query.id))
    if query.steamid64 is not None:
        filters.append(col(Record.steamid64) == query.steamid64)
    if query.server_id is not None:
        filters.append(col(Record.server_id) == query.server_id)
    if query.mode_id is not None:
        filters.append(col(Record.mode_id) == query.mode_id)
    if query.map_id is not None:
        filters.append(col(Record.map_id) == query.map_id)
    if query.stage is not None:
        filters.append(col(Record.stage) == query.stage)
    if query.teleports is not None:
        filters.append(col(Record.teleports) == query.teleports)
    if query.replay_id is not None:
        filters.append(col(Record.replay_id) == query.replay_id)
    if query.is_valid is not None:
        filters.append(col(Record.is_valid) == query.is_valid)
    if query.created_since is not None:
        filters.append(col(Record.created_on) >= query.created_since)
    if query.updated_since is not None:
        filters.append(col(Record.updated_on) >= query.updated_since)

    count_statement = select(func.count()).select_from(Record)
    statement = select(Record)
    for condition in filters:
        count_statement = count_statement.where(condition)
        statement = statement.where(condition)

    count = (await session.exec(count_statement)).one()
    statement = (
        statement.order_by(col(Record.created_on).desc(), col(Record.uuid).desc())
        .offset(query.offset)
        .limit(query.limit)
    )
    records = list((await session.exec(statement)).all())
    return records, count


async def read_recent_records(
    *,
    session: AsyncSession,
    query: RecentRecordListQuery,
) -> tuple[list[RecentRecordPublic], int]:
    count = await _estimate_record_count(session=session, is_valid=True)

    statement = (
        select(Record, Player, ServerGlobalapi, Map, Mode)
        .join(Player, col(Record.steamid64) == col(Player.steamid64))
        .join(ServerGlobalapi, col(Record.server_id) == col(ServerGlobalapi.id))
        .join(Map, col(Record.map_id) == col(Map.id))
        .join(Mode, col(Record.mode_id) == col(Mode.id))
        .where(col(Record.is_valid).is_(True))
        .order_by(
            col(Record.created_on).desc(),
            col(Record.id).desc().nullslast(),
            col(Record.uuid).desc(),
        )
        .offset(query.offset)
        .limit(query.limit)
    )
    rows = (await session.exec(statement)).all()
    return (
        [
            to_recent_record_public(
                record=record,
                player=player,
                server=server,
                map_obj=map_obj,
                mode=mode,
            )
            for record, player, server, map_obj, mode in rows
        ],
        count,
    )


async def get_record_by_uuid(
    *,
    session: AsyncSession,
    record_uuid: uuid.UUID,
) -> Record | None:
    return await session.get(Record, record_uuid)


async def get_record_by_id(
    *,
    session: AsyncSession,
    record_id: int,
) -> Record | None:
    statement = select(Record).where(col(Record.id) == record_id).limit(1)
    return (await session.exec(statement)).first()


async def get_recent_record_public_by_uuid(
    *,
    session: AsyncSession,
    record_uuid: uuid.UUID,
) -> RecentRecordPublic | None:
    statement = (
        select(Record, Player, ServerGlobalapi, Map, Mode)
        .join(Player, col(Record.steamid64) == col(Player.steamid64))
        .join(ServerGlobalapi, col(Record.server_id) == col(ServerGlobalapi.id))
        .join(Map, col(Record.map_id) == col(Map.id))
        .join(Mode, col(Record.mode_id) == col(Mode.id))
        .where(col(Record.uuid) == record_uuid)
        .limit(1)
    )
    row = (await session.exec(statement)).first()
    if row is None:
        return None

    record, player, server, map_obj, mode = row
    return to_recent_record_public(
        record=record,
        player=player,
        server=server,
        map_obj=map_obj,
        mode=mode,
    )


async def notify_recent_record_updated(
    *,
    session: AsyncSession,
    record_uuid: uuid.UUID,
) -> None:
    await session.execute(
        text(f"SELECT pg_notify('{RECENT_RECORD_NOTIFY_CHANNEL}', :record_uuid)"),
        {"record_uuid": str(record_uuid)},
    )


async def upsert_record(
    *,
    session: AsyncSession,
    record_id: int | None,
    record_uuid: uuid.UUID | None,
    steamid64: int,
    server_id: int,
    mode_id: int,
    map_id: int,
    stage: int,
    time_seconds: Decimal,
    teleports: int,
    points: int,
    created_on: datetime,
    updated_on: datetime,
    updated_by: int,
    replay_id: int | None,
    is_valid: bool,
) -> tuple[Record, bool, bool]:
    existing_record = (
        await get_record_by_id(session=session, record_id=record_id)
        if record_id is not None
        else None
    )
    if existing_record is None:
        record = Record(
            uuid=record_uuid or generate_uuid7(timestamp=created_on),
            id=record_id,
            steamid64=steamid64,
            server_id=server_id,
            mode_id=mode_id,
            map_id=map_id,
            stage=stage,
            time=time_seconds,
            teleports=teleports,
            points=points,
            created_on=created_on,
            updated_on=updated_on,
            updated_by=updated_by,
            replay_id=replay_id,
            is_valid=is_valid,
        )
        session.add(record)
        return record, True, False

    existing_record.steamid64 = steamid64
    existing_record.server_id = server_id
    existing_record.mode_id = mode_id
    existing_record.map_id = map_id
    existing_record.stage = stage
    existing_record.time = time_seconds
    existing_record.teleports = teleports
    existing_record.points = points
    existing_record.created_on = created_on
    existing_record.updated_on = updated_on
    existing_record.updated_by = updated_by
    existing_record.replay_id = replay_id
    existing_record.is_valid = is_valid
    session.add(existing_record)
    return existing_record, False, True


async def update_record_validity(
    *,
    session: AsyncSession,
    record: Record,
    patch: RecordPatch,
) -> Record:
    record.is_valid = patch.is_valid
    record.updated_on = get_datetime_utc()
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


async def get_max_record_globalapi_id(*, session: AsyncSession) -> int | None:
    statement = select(func.max(Record.id)).where(Record.id.is_not(None))
    return (await session.exec(statement)).one()


def _apply_teleports_type(
    statement,
    teleports_type: TeleportsType,
):
    if teleports_type == TeleportsType.PRO:
        return statement.where(col(Record.teleports) == 0)
    if teleports_type == TeleportsType.NUB:
        return statement.where(col(Record.teleports) > 0)
    return statement


async def get_pb_records(
    session: AsyncSession,
    *,
    map_id: int | None,
    stage: int,
    steamid64: int | None,
    mode_ids: Sequence[int],
    teleports_type: TeleportsType,
    server_ids: Sequence[int] | None,
) -> list[Record]:
    statement = select(Record).where(col(Record.is_valid).is_(True))
    if mode_ids:
        statement = statement.where(col(Record.mode_id).in_(list(mode_ids)))
    if server_ids:
        statement = statement.where(col(Record.server_id).in_(list(server_ids)))

    if map_id is not None:
        statement = statement.where(
            col(Record.map_id) == map_id,
            col(Record.stage) == stage,
        )
        statement = _apply_teleports_type(statement, teleports_type)
        subquery = (
            statement.with_only_columns(Record.uuid)
            .distinct(col(Record.steamid64))
            .order_by(
                col(Record.steamid64),
                col(Record.time).asc(),
                *_record_tie_breakers(),
            )
            .subquery()
        )
        final_statement = (
            select(Record)
            .join(subquery, col(Record.uuid) == subquery.c.uuid)
            .order_by(
                col(Record.time).asc(),
                *_record_tie_breakers(),
            )
        )
        return list((await session.exec(final_statement)).all())

    if steamid64 is not None:
        statement = statement.where(col(Record.steamid64) == steamid64)
        statement = _apply_teleports_type(statement, teleports_type)
        subquery = (
            statement.with_only_columns(Record.uuid)
            .distinct(col(Record.map_id), col(Record.stage))
            .order_by(
                col(Record.map_id),
                col(Record.stage),
                col(Record.time).asc(),
                *_record_tie_breakers(),
            )
            .subquery()
        )
        final_statement = (
            select(Record)
            .join(subquery, col(Record.uuid) == subquery.c.uuid)
            .order_by(
                col(Record.map_id).asc(),
                col(Record.stage).asc(),
            )
        )
        return list((await session.exec(final_statement)).all())

    return []


def _teleports_bucket_expression():
    return case((col(Record.teleports) == 0, 0), else_=1)


async def get_record_place(
    *,
    session: AsyncSession,
    record: Record,
) -> int:
    teleports_condition = (
        col(Record.teleports) == 0 if record.teleports == 0 else col(Record.teleports) > 0
    )
    better_statement = select(func.count()).select_from(Record).where(
        col(Record.is_valid).is_(True),
        col(Record.id).is_not(None),
        col(Record.map_id) == record.map_id,
        col(Record.mode_id) == record.mode_id,
        col(Record.stage) == record.stage,
        teleports_condition,
        (
            (col(Record.time) < record.time)
            | (
                (col(Record.time) == record.time)
                & (
                    (col(Record.id) < record.id)
                    | (
                        col(Record.id).is_(None)
                        & (col(Record.uuid) < record.uuid)
                    )
                )
            )
        ),
    )
    better_count = (await session.exec(better_statement)).one()
    return better_count + 1


async def get_top_records_v0(
    *,
    session: AsyncSession,
    steamid64: int | None,
    server_id: int | None,
    map_id: int | None,
    map_name: str | None,
    mode_ids: Sequence[int],
    stage: int,
    has_teleports: bool | None,
    player_name: str | None,
    offset: int,
    limit: int,
) -> list[Record]:
    teleports_type = TeleportsType.OVR
    if has_teleports is True:
        teleports_type = TeleportsType.NUB
    elif has_teleports is False:
        teleports_type = TeleportsType.PRO

    resolved_map_id = map_id
    if resolved_map_id is None and map_name is not None:
        map_statement = select(Map).where(col(Map.name) == map_name).limit(1)
        map_obj = (await session.exec(map_statement)).first()
        if map_obj is None:
            return []
        resolved_map_id = map_obj.id

    if player_name:
        player_statement = select(Player.steamid64).where(
            col(Player.name).ilike(f"%{player_name}%")
        )
        player_ids = list((await session.exec(player_statement)).all())
        if not player_ids:
            return []
        if steamid64 is not None and steamid64 not in player_ids:
            return []
        if steamid64 is None:
            # For name searches without an explicit steamid, fall back to direct rows.
            statement = select(Record).where(
                col(Record.is_valid).is_(True),
                col(Record.id).is_not(None),
                col(Record.steamid64).in_(player_ids),
            )
            if resolved_map_id is not None:
                statement = statement.where(col(Record.map_id) == resolved_map_id)
            if server_id is not None:
                statement = statement.where(col(Record.server_id) == server_id)
            if mode_ids:
                statement = statement.where(col(Record.mode_id).in_(list(mode_ids)))
            statement = _apply_teleports_type(statement, teleports_type)
            statement = statement.where(col(Record.stage) == stage)
            statement = statement.order_by(col(Record.time).asc(), *_record_tie_breakers())
            statement = statement.offset(offset).limit(limit)
            return list((await session.exec(statement)).all())

    if resolved_map_id is not None or steamid64 is not None:
        records = await get_pb_records(
            session,
            map_id=resolved_map_id,
            stage=stage,
            steamid64=steamid64,
            mode_ids=mode_ids,
            teleports_type=teleports_type,
            server_ids=[server_id] if server_id is not None else None,
        )
        return records[offset : offset + limit]

    return []


async def get_world_record_counts_v0(
    *,
    session: AsyncSession,
    ids: Sequence[int] | None,
    map_ids: Sequence[int] | None,
    stages: Sequence[int] | None,
    mode_ids: Sequence[int] | None,
    has_teleports: bool | None,
    offset: int,
    limit: int,
) -> list[WorldRecordCountCompatPublicV0]:
    statement = select(Record).where(
        col(Record.is_valid).is_(True),
        col(Record.id).is_not(None),
    )
    if ids:
        statement = statement.where(col(Record.id).in_(list(ids)))
    if map_ids:
        statement = statement.where(col(Record.map_id).in_(list(map_ids)))
    if stages:
        statement = statement.where(col(Record.stage).in_(list(stages)))
    if mode_ids:
        statement = statement.where(col(Record.mode_id).in_(list(mode_ids)))
    if has_teleports is True:
        statement = statement.where(col(Record.teleports) > 0)
        distinct_columns = [col(Record.map_id), col(Record.stage), col(Record.mode_id)]
        order_columns = [
            col(Record.map_id),
            col(Record.stage),
            col(Record.mode_id),
            col(Record.time).asc(),
            *_record_tie_breakers(),
        ]
    elif has_teleports is False:
        statement = statement.where(col(Record.teleports) == 0)
        distinct_columns = [col(Record.map_id), col(Record.stage), col(Record.mode_id)]
        order_columns = [
            col(Record.map_id),
            col(Record.stage),
            col(Record.mode_id),
            col(Record.time).asc(),
            *_record_tie_breakers(),
        ]
    else:
        bucket = _teleports_bucket_expression()
        distinct_columns = [
            col(Record.map_id),
            col(Record.stage),
            col(Record.mode_id),
            bucket,
        ]
        order_columns = [
            col(Record.map_id),
            col(Record.stage),
            col(Record.mode_id),
            bucket,
            col(Record.time).asc(),
            *_record_tie_breakers(),
        ]

    winner_ids = (
        statement.with_only_columns(Record.uuid)
        .distinct(*distinct_columns)
        .order_by(*order_columns)
        .subquery()
    )
    winners_statement = select(Record).join(
        winner_ids, col(Record.uuid) == winner_ids.c.uuid
    )
    winners = list((await session.exec(winners_statement)).all())
    counts: dict[int, int] = {}
    for winner in winners:
        counts[winner.steamid64] = counts.get(winner.steamid64, 0) + 1

    sorted_counts = sorted(
        counts.items(),
        key=lambda item: (-item[1], item[0]),
    )
    sliced_counts = sorted_counts[offset : offset + limit]

    results: list[WorldRecordCountCompatPublicV0] = []
    for player_id, wr_count in sliced_counts:
        player = await session.get(Player, player_id)
        if player is None:
            continue
        results.append(
            WorldRecordCountCompatPublicV0(
                steamid64=player_id,
                player_name=player.name,
                steam_id=None,
                world_records=wr_count,
            )
        )
    return results


async def get_recent_top_records_v0(
    *,
    session: AsyncSession,
    steamid64: int | None,
    map_id: int | None,
    map_name: str | None,
    mode_ids: Sequence[int],
    stage: int | None,
    has_teleports: bool | None,
    created_since: datetime | None,
    place_top_at_least: int | None,
    place_top_overall_at_least: int | None,
    offset: int,
    limit: int,
) -> list[RecentRecordCompatPublicV0]:
    statement = select(Record).where(
        col(Record.is_valid).is_(True),
        col(Record.id).is_not(None),
    )
    if steamid64 is not None:
        statement = statement.where(col(Record.steamid64) == steamid64)
    if map_id is not None:
        statement = statement.where(col(Record.map_id) == map_id)
    if map_id is None and map_name is not None:
        statement = statement.join(Map, col(Record.map_id) == col(Map.id)).where(
            col(Map.name) == map_name
        )
    if mode_ids:
        statement = statement.where(col(Record.mode_id).in_(list(mode_ids)))
    if stage is not None:
        statement = statement.where(col(Record.stage) == stage)
    if has_teleports is True:
        statement = statement.where(col(Record.teleports) > 0)
    elif has_teleports is False:
        statement = statement.where(col(Record.teleports) == 0)
    if created_since is not None:
        statement = statement.where(col(Record.created_on) >= created_since)

    statement = statement.order_by(
        col(Record.created_on).desc(),
        col(Record.id).desc().nullslast(),
        col(Record.uuid).desc(),
    )
    recent_records = list((await session.exec(statement)).all())

    results: list[RecentRecordCompatPublicV0] = []
    for record in recent_records:
        place = await get_record_place(session=session, record=record)

        overall_statement = select(func.count()).select_from(Record).where(
            col(Record.is_valid).is_(True),
            col(Record.id).is_not(None),
            col(Record.map_id) == record.map_id,
            col(Record.mode_id) == record.mode_id,
            col(Record.stage) == record.stage,
            (
                (col(Record.time) < record.time)
                | (
                    (col(Record.time) == record.time)
                    & (
                        (col(Record.id) < record.id)
                        | (
                            col(Record.id).is_(None)
                            & (col(Record.uuid) < record.uuid)
                        )
                    )
                )
            ),
        )
        place_overall = (await session.exec(overall_statement)).one() + 1

        if place_top_at_least is not None and place > place_top_at_least:
            continue
        if (
            place_top_overall_at_least is not None
            and place_overall > place_top_overall_at_least
        ):
            continue

        player, server, map_obj, mode = await _load_record_context(
            session=session,
            record=record,
        )
        compat = to_record_compat_public_v0(
            record=record,
            player=player,
            server=server,
            map_obj=map_obj,
            mode=mode,
        )
        results.append(
            RecentRecordCompatPublicV0(
                **compat.model_dump(),
                place=place,
                place_overall=place_overall,
                top_100=place <= 100,
                top_100_overall=place_overall <= 100,
            )
        )

    return results[offset : offset + limit]
