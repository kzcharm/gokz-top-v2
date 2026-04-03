import uuid
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from sqlalchemy import and_, case, func, text, true
from sqlalchemy.orm import aliased
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    Map,
    MapCourse,
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
    RecordPb,
    RecordPublic,
    RecordScope,
    ServerGlobalapi,
    ServerGlobalapiCompatPublicV0,
    TeleportsType,
    WorldRecordCountCompatPublicV0,
    generate_uuid7,
    get_datetime_utc,
    scope_mode_ids,
    scope_to_id,
    seconds_to_time_ms,
)

from .record_filter import load_scoped_course_tiers

RECENT_RECORD_NOTIFY_CHANNEL = "recent_record_updates"
RECENT_RECORD_EXACT_COUNT_THRESHOLD = 100_000


def _record_tie_breakers() -> tuple:
    return (
        col(Record.id).asc().nullslast(),
        col(Record.uuid).asc(),
    )


def _resolve_scoped_points(
    *,
    pro_points: int | None,
    ovr_points: int | None,
) -> int:
    if pro_points is not None:
        return pro_points
    if ovr_points is not None:
        return ovr_points
    return 0


async def _get_or_create_map_course(
    *,
    session: AsyncSession,
    map_id: int,
    stage: int,
) -> MapCourse:
    statement = (
        select(MapCourse)
        .where(col(MapCourse.map_id) == map_id, col(MapCourse.stage) == stage)
        .limit(1)
    )
    course = (await session.exec(statement)).first()
    if course is not None:
        return course

    course = MapCourse(map_id=map_id, stage=stage)
    session.add(course)
    await session.flush()
    return course


async def _get_map_course_by_id(
    *,
    session: AsyncSession,
    course_id: int,
) -> MapCourse | None:
    return await session.get(MapCourse, course_id)


async def _get_map_course_by_map_stage(
    *,
    session: AsyncSession,
    map_id: int,
    stage: int,
) -> MapCourse | None:
    statement = (
        select(MapCourse)
        .where(col(MapCourse.map_id) == map_id, col(MapCourse.stage) == stage)
        .limit(1)
    )
    return (await session.exec(statement)).first()


async def _load_pb_points_by_record_uuid(
    *,
    session: AsyncSession,
    record_uuids: Sequence[uuid.UUID],
    scope: RecordScope,
) -> dict[uuid.UUID, int]:
    if not record_uuids:
        return {}

    scope_id = scope_to_id(scope)
    statement = select(RecordPb.record_uuid, RecordPb.is_pro_only, RecordPb.points).where(
        col(RecordPb.record_uuid).in_(list(record_uuids)),
        col(RecordPb.scope) == scope_id,
    )
    points_by_uuid: dict[uuid.UUID, dict[bool, int]] = {}
    for record_uuid, is_pro_only, points in (await session.exec(statement)).all():
        current = points_by_uuid.setdefault(record_uuid, {})
        current[is_pro_only] = points

    return {
        record_uuid: _resolve_scoped_points(
            pro_points=values.get(True),
            ovr_points=values.get(False),
        )
        for record_uuid, values in points_by_uuid.items()
    }


async def load_scoped_points_by_record_uuid(
    *,
    session: AsyncSession,
    record_uuids: Sequence[uuid.UUID],
    scope: RecordScope,
) -> dict[uuid.UUID, int]:
    return await _load_pb_points_by_record_uuid(
        session=session,
        record_uuids=record_uuids,
        scope=scope,
    )


async def _load_scoped_record_tiers(
    *,
    session: AsyncSession,
    record_courses: Sequence[tuple[int, int]],
    scope: RecordScope,
) -> dict[tuple[int, int], int]:
    return await load_scoped_course_tiers(
        session=session,
        course_keys=record_courses,
        scope=scope,
    )


def _pb_key_candidates_for_record(
    *,
    scope_ids: Sequence[int],
    course_id: int,
    steamid64: int,
    teleports: int,
    is_valid: bool,
) -> set[tuple[int, int, int, bool]]:
    if not is_valid:
        return set()

    keys = {
        (scope_id, course_id, steamid64, False)
        for scope_id in scope_ids
    }
    if teleports == 0:
        keys |= {
            (scope_id, course_id, steamid64, True)
            for scope_id in scope_ids
        }
    return keys


def _scope_ids_for_mode_id(mode_id: int) -> tuple[int, ...]:
    return tuple(
        scope_id
        for scope_id, mode_ids in (
            (scope_to_id(RecordScope.OVR), scope_mode_ids(scope_to_id(RecordScope.OVR))),
            (scope_to_id(RecordScope.KZT), scope_mode_ids(scope_to_id(RecordScope.KZT))),
            (scope_to_id(RecordScope.SKZ), scope_mode_ids(scope_to_id(RecordScope.SKZ))),
            (scope_to_id(RecordScope.VNL), scope_mode_ids(scope_to_id(RecordScope.VNL))),
        )
        if mode_id in mode_ids
    )


async def _select_pb_winner(
    *,
    session: AsyncSession,
    scope_id: int,
    course_id: int,
    steamid64: int,
    is_pro_only: bool,
) -> Record | None:
    course = await _get_map_course_by_id(session=session, course_id=course_id)
    if course is None:
        return None

    statement = (
        select(Record)
        .where(
            col(Record.is_valid) == true(),
            col(Record.steamid64) == steamid64,
            col(Record.map_id) == course.map_id,
            col(Record.stage) == course.stage,
            col(Record.mode_id).in_(list(scope_mode_ids(scope_id))),
        )
        .order_by(col(Record.time).asc(), *_record_tie_breakers())
        .limit(1)
    )
    if is_pro_only:
        statement = statement.where(col(Record.teleports) == 0)

    return (await session.exec(statement)).first()


async def recompute_record_pbs_for_keys(
    *,
    session: AsyncSession,
    keys: set[tuple[int, int, int, bool]],
) -> None:
    for scope_id, course_id, steamid64, is_pro_only in keys:
        existing = (
            await session.exec(
                select(RecordPb).where(
                    col(RecordPb.scope) == scope_id,
                    col(RecordPb.course_id) == course_id,
                    col(RecordPb.steamid64) == steamid64,
                    col(RecordPb.is_pro_only).is_(is_pro_only),
                )
            )
        ).first()

        winner = await _select_pb_winner(
            session=session,
            scope_id=scope_id,
            course_id=course_id,
            steamid64=steamid64,
            is_pro_only=is_pro_only,
        )
        if winner is None:
            if existing is not None:
                await session.delete(existing)
            continue

        if existing is None:
            session.add(
                RecordPb(
                    scope=scope_id,
                    course_id=course_id,
                    steamid64=steamid64,
                    is_pro_only=is_pro_only,
                    record_uuid=winner.uuid,
                    time_ms=seconds_to_time_ms(winner.time),
                    points=1,
                    updated_on=get_datetime_utc(),
                )
            )
            continue

        existing.record_uuid = winner.uuid
        existing.time_ms = seconds_to_time_ms(winner.time)
        existing.updated_on = get_datetime_utc()
        if existing.points < 1:
            existing.points = 1
        session.add(existing)


async def rebuild_record_pbs(*, session: AsyncSession) -> None:
    await ensure_map_courses_for_valid_records(session=session)
    courses = (
        await session.exec(
            select(MapCourse)
            .join(
                Record,
                and_(
                    col(Record.map_id) == col(MapCourse.map_id),
                    col(Record.stage) == col(MapCourse.stage),
                ),
            )
            .where(col(Record.is_valid) == true())
            .distinct()
            .order_by(col(MapCourse.map_id), col(MapCourse.stage), col(MapCourse.id))
        )
    ).all()
    for course in courses:
        if course.id is None:
            continue
        await rebuild_record_pbs_for_course(
            session=session,
            course_id=course.id,
            map_id=course.map_id,
            stage=course.stage,
        )


async def ensure_map_courses_for_valid_records(*, session: AsyncSession) -> None:
    await session.exec(
        text(
            """
            INSERT INTO map_course (map_id, stage)
            SELECT DISTINCT record.map_id, record.stage
            FROM record
            WHERE record.is_valid = true
            ON CONFLICT (map_id, stage) DO NOTHING
            """
        )
    )


async def rebuild_record_pbs_for_course(
    *,
    session: AsyncSession,
    course_id: int,
    map_id: int,
    stage: int,
) -> None:
    await session.exec(
        text(
            """
            WITH existing_points AS (
                SELECT
                    record_pb.scope,
                    record_pb.steamid64,
                    record_pb.is_pro_only,
                    record_pb.points
                FROM record_pb
                WHERE record_pb.course_id = :course_id
            ),
            deleted_rows AS (
                DELETE FROM record_pb
                WHERE record_pb.course_id = :course_id
                RETURNING record_pb.scope, record_pb.steamid64, record_pb.is_pro_only
            ),
            scope_modes(scope, mode_id) AS (
                VALUES
                    (0, 200),
                    (0, 201),
                    (0, 202),
                    (0, 203),
                    (1, 200),
                    (1, 203),
                    (2, 201),
                    (3, 202)
            ),
            pro_filters(is_pro_only) AS (
                VALUES
                    (FALSE),
                    (TRUE)
            ),
            ranked_records AS (
                SELECT
                    scope_modes.scope,
                    record.steamid64,
                    pro_filters.is_pro_only,
                    record.uuid AS record_uuid,
                    ROUND(record.time * 1000)::bigint AS time_ms,
                    ROW_NUMBER() OVER (
                        PARTITION BY
                            scope_modes.scope,
                            record.steamid64,
                            pro_filters.is_pro_only
                        ORDER BY
                            record.time ASC,
                            record.id ASC NULLS LAST,
                            record.uuid ASC
                    ) AS row_number
                FROM record
                JOIN scope_modes
                    ON scope_modes.mode_id = record.mode_id
                JOIN pro_filters
                    ON (
                        NOT pro_filters.is_pro_only
                        OR record.teleports = 0
                    )
                WHERE record.is_valid = true
                    AND record.map_id = :map_id
                    AND record.stage = :stage
            )
            INSERT INTO record_pb (
                scope,
                course_id,
                steamid64,
                is_pro_only,
                record_uuid,
                time_ms,
                points,
                updated_on
            )
            SELECT
                ranked_records.scope,
                :course_id,
                ranked_records.steamid64,
                ranked_records.is_pro_only,
                ranked_records.record_uuid,
                ranked_records.time_ms,
                COALESCE(existing_points.points, 1),
                :updated_on
            FROM ranked_records
            LEFT JOIN existing_points
                ON existing_points.scope = ranked_records.scope
                AND existing_points.steamid64 = ranked_records.steamid64
                AND existing_points.is_pro_only = ranked_records.is_pro_only
            WHERE ranked_records.row_number = 1
            ON CONFLICT (scope, course_id, steamid64, is_pro_only)
            DO UPDATE SET
                record_uuid = EXCLUDED.record_uuid,
                time_ms = EXCLUDED.time_ms,
                points = GREATEST(record_pb.points, EXCLUDED.points),
                updated_on = EXCLUDED.updated_on
            """
        ),
        params={
            "course_id": course_id,
            "map_id": map_id,
            "stage": stage,
            "updated_on": get_datetime_utc(),
        },
    )


async def _pb_keys_for_record_snapshot(
    *,
    session: AsyncSession,
    map_id: int,
    stage: int,
    mode_id: int,
    steamid64: int,
    teleports: int,
    is_valid: bool,
) -> set[tuple[int, int, int, bool]]:
    course = await _get_or_create_map_course(session=session, map_id=map_id, stage=stage)
    if course.id is None:
        return set()
    return _pb_key_candidates_for_record(
        scope_ids=_scope_ids_for_mode_id(mode_id),
        course_id=course.id,
        steamid64=steamid64,
        teleports=teleports,
        is_valid=is_valid,
    )


async def _refresh_record_pbs_for_change(
    *,
    session: AsyncSession,
    before: Record | None,
    after: Record | None,
) -> None:
    keys: set[tuple[int, int, int, bool]] = set()
    if before is not None:
        keys |= await _pb_keys_for_record_snapshot(
            session=session,
            map_id=before.map_id,
            stage=before.stage,
            mode_id=before.mode_id,
            steamid64=before.steamid64,
            teleports=before.teleports,
            is_valid=True,
        )
    if after is not None:
        keys |= await _pb_keys_for_record_snapshot(
            session=session,
            map_id=after.map_id,
            stage=after.stage,
            mode_id=after.mode_id,
            steamid64=after.steamid64,
            teleports=after.teleports,
            is_valid=after.is_valid,
        )
    await recompute_record_pbs_for_keys(session=session, keys=keys)

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
    map_tier: int,
    points: int,
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
        map_tier=map_tier,
        mode_id=record.mode_id,
        mode=mode.name_short,
        stage=record.stage,
        tickrate=128,
        time=float(record.time),
        teleports=record.teleports,
        points=points,
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
    map_tier: int,
    points: int,
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
            tier=map_tier,
        ),
        server=RecentRecordServerPublic(
            id=server.id,
            name=server.name or "",
        ),
        mode=RecentRecordModePublic(
            id=mode.id,
            name=mode.name_short,
        ),
        stage=record.stage,
        teleports=record.teleports,
        time=float(record.time),
        points=points,
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
    scope_id = scope_to_id(query.scope)
    pro_pb = aliased(RecordPb)
    ovr_pb = aliased(RecordPb)
    scoped_points = func.coalesce(pro_pb.points, ovr_pb.points, 0)

    statement = (
        select(Record, Player, ServerGlobalapi, Map, Mode, scoped_points.label("points"))
        .join(Player, col(Record.steamid64) == col(Player.steamid64))
        .join(ServerGlobalapi, col(Record.server_id) == col(ServerGlobalapi.id))
        .join(Map, col(Record.map_id) == col(Map.id))
        .join(Mode, col(Record.mode_id) == col(Mode.id))
        .outerjoin(
            pro_pb,
            and_(
                pro_pb.record_uuid == Record.uuid,
                pro_pb.scope == scope_id,
                pro_pb.is_pro_only.is_(True),
            ),
        )
        .outerjoin(
            ovr_pb,
            and_(
                ovr_pb.record_uuid == Record.uuid,
                ovr_pb.scope == scope_id,
                ovr_pb.is_pro_only.is_(False),
            ),
        )
        .where(col(Record.is_valid).is_(True))
    )
    if query.is_pro_only is True:
        statement = statement.where(col(Record.teleports) == 0)
    if query.points_more_or_equal_than is not None:
        statement = statement.where(scoped_points >= query.points_more_or_equal_than)

    if query.points_more_or_equal_than is None and query.is_pro_only is not True:
        count = await _estimate_record_count(session=session, is_valid=True)
    else:
        count_statement = (
            select(func.count())
            .select_from(Record)
            .outerjoin(
                pro_pb,
                and_(
                    pro_pb.record_uuid == Record.uuid,
                    pro_pb.scope == scope_id,
                    pro_pb.is_pro_only.is_(True),
                ),
            )
            .outerjoin(
                ovr_pb,
                and_(
                    ovr_pb.record_uuid == Record.uuid,
                    ovr_pb.scope == scope_id,
                    ovr_pb.is_pro_only.is_(False),
                ),
            )
            .where(col(Record.is_valid).is_(True))
        )
        if query.is_pro_only is True:
            count_statement = count_statement.where(col(Record.teleports) == 0)
        if query.points_more_or_equal_than is not None:
            count_statement = count_statement.where(
                func.coalesce(pro_pb.points, ovr_pb.points, 0)
                >= query.points_more_or_equal_than
            )
        count = (await session.exec(count_statement)).one()

    rows = (
        await session.exec(
            statement.order_by(
                col(Record.created_on).desc(),
                col(Record.id).desc().nullslast(),
                col(Record.uuid).desc(),
            )
            .offset(query.offset)
            .limit(query.limit)
        )
    ).all()
    tiers_by_course = await _load_scoped_record_tiers(
        session=session,
        record_courses=[
            (record.map_id, record.stage)
            for record, _player, _server, _map_obj, _mode, _points in rows
        ],
        scope=query.scope,
    )
    return (
        [
            to_recent_record_public(
                record=record,
                player=player,
                server=server,
                map_obj=map_obj,
                mode=mode,
                map_tier=tiers_by_course[(record.map_id, record.stage)],
                points=points,
            )
            for record, player, server, map_obj, mode, points in rows
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
    scope: RecordScope = RecordScope.OVR,
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
    scoped_points = (await _load_pb_points_by_record_uuid(
        session=session,
        record_uuids=[record.uuid],
        scope=scope,
    )).get(record.uuid, 0)
    map_tier = (
        await _load_scoped_record_tiers(
            session=session,
            record_courses=[(record.map_id, record.stage)],
            scope=scope,
        )
    )[(record.map_id, record.stage)]
    return to_recent_record_public(
        record=record,
        player=player,
        server=server,
        map_obj=map_obj,
        mode=mode,
        map_tier=map_tier,
        points=scoped_points,
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
        await _refresh_record_pbs_for_change(session=session, before=None, after=record)
        return record, True, False

    before_record = Record.model_validate(existing_record.model_dump())
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
    await _refresh_record_pbs_for_change(
        session=session,
        before=before_record,
        after=existing_record,
    )
    return existing_record, False, True


async def update_record_validity(
    *,
    session: AsyncSession,
    record: Record,
    patch: RecordPatch,
) -> Record:
    before_record = Record.model_validate(record.model_dump())
    record.is_valid = patch.is_valid
    record.updated_on = get_datetime_utc()
    session.add(record)
    await _refresh_record_pbs_for_change(
        session=session,
        before=before_record,
        after=record,
    )
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


async def _get_pb_records_v0(
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


async def get_pb_records(
    session: AsyncSession,
    *,
    map_id: int | None,
    stage: int,
    steamid64: int | None,
    scope: RecordScope,
    is_pro_only: bool,
    offset: int = 0,
    limit: int = 100,
) -> list[Record]:
    scope_id = scope_to_id(scope)

    if map_id is not None:
        course = await _get_map_course_by_map_stage(
            session=session,
            map_id=map_id,
            stage=stage,
        )
        if course is None or course.id is None:
            return []

        statement = (
            select(Record)
            .join(RecordPb, RecordPb.record_uuid == Record.uuid)
            .where(
                RecordPb.scope == scope_id,
                RecordPb.course_id == course.id,
                RecordPb.is_pro_only.is_(is_pro_only),
            )
            .order_by(RecordPb.time_ms.asc(), RecordPb.record_uuid.asc())
            .offset(offset)
            .limit(limit)
        )
        return list((await session.exec(statement)).all())

    if steamid64 is not None:
        course = aliased(MapCourse)
        statement = (
            select(Record)
            .join(RecordPb, RecordPb.record_uuid == Record.uuid)
            .join(course, course.id == RecordPb.course_id)
            .where(
                RecordPb.scope == scope_id,
                RecordPb.steamid64 == steamid64,
                RecordPb.is_pro_only.is_(is_pro_only),
                course.stage == stage,
            )
            .order_by(
                course.map_id.asc(),
                course.stage.asc(),
                RecordPb.time_ms.asc(),
                RecordPb.record_uuid.asc(),
            )
            .offset(offset)
            .limit(limit)
        )
        return list((await session.exec(statement)).all())

    return []


async def get_pb_record_publics(
    session: AsyncSession,
    *,
    map_id: int | None,
    stage: int,
    steamid64: int | None,
    scope: RecordScope,
    is_pro_only: bool,
    offset: int = 0,
    limit: int = 100,
) -> list[RecordPublic]:
    scope_id = scope_to_id(scope)
    anchor_pb = aliased(RecordPb)
    pro_pb = aliased(RecordPb)
    ovr_pb = aliased(RecordPb)
    scoped_points = func.coalesce(pro_pb.points, ovr_pb.points, 0)

    statement = (
        select(
            Record.uuid,
            Record.id,
            Record.steamid64,
            Player.name,
            Player.avatar_hash,
            Record.server_id,
            ServerGlobalapi.name.label("server_name"),
            Record.map_id,
            Map.name.label("map_name"),
            Map.difficulty,
            Record.mode_id,
            Mode.name_short,
            Record.stage,
            Record.time,
            Record.teleports,
            scoped_points.label("points"),
            Record.created_on,
            Record.updated_on,
            Record.updated_by,
            Record.replay_id,
            Record.is_valid,
        )
        .join(anchor_pb, anchor_pb.record_uuid == Record.uuid)
        .join(Player, col(Record.steamid64) == col(Player.steamid64))
        .join(ServerGlobalapi, col(Record.server_id) == col(ServerGlobalapi.id))
        .join(Map, col(Record.map_id) == col(Map.id))
        .join(Mode, col(Record.mode_id) == col(Mode.id))
        .outerjoin(
            pro_pb,
            and_(
                pro_pb.record_uuid == Record.uuid,
                pro_pb.scope == scope_id,
                pro_pb.is_pro_only.is_(True),
            ),
        )
        .outerjoin(
            ovr_pb,
            and_(
                ovr_pb.record_uuid == Record.uuid,
                ovr_pb.scope == scope_id,
                ovr_pb.is_pro_only.is_(False),
            ),
        )
    )

    if map_id is not None:
        course = await _get_map_course_by_map_stage(
            session=session,
            map_id=map_id,
            stage=stage,
        )
        if course is None or course.id is None:
            return []

        statement = statement.where(
            anchor_pb.scope == scope_id,
            anchor_pb.course_id == course.id,
            anchor_pb.is_pro_only.is_(is_pro_only),
        ).order_by(anchor_pb.time_ms.asc(), anchor_pb.record_uuid.asc())
    elif steamid64 is not None:
        course = aliased(MapCourse)
        statement = (
            statement.join(course, course.id == anchor_pb.course_id)
            .where(
                anchor_pb.scope == scope_id,
                anchor_pb.steamid64 == steamid64,
                anchor_pb.is_pro_only.is_(is_pro_only),
                course.stage == stage,
            )
            .order_by(
                course.map_id.asc(),
                course.stage.asc(),
                anchor_pb.time_ms.asc(),
                anchor_pb.record_uuid.asc(),
            )
        )
    else:
        return []

    rows = (await session.exec(statement.offset(offset).limit(limit))).all()
    tiers_by_course = await _load_scoped_record_tiers(
        session=session,
        record_courses=[
            (record_map_id, record_stage)
            for (
                _record_uuid,
                _record_id,
                _record_steamid64,
                _player_name,
                _player_avatar_hash,
                _server_id,
                _server_name,
                record_map_id,
                _map_name,
                _map_tier,
                _record_mode_id,
                _mode_name,
                record_stage,
                _record_time,
                _record_teleports,
                _points,
                _created_on,
                _updated_on,
                _updated_by,
                _replay_id,
                _is_valid,
            ) in rows
        ],
        scope=scope,
    )
    return [
        RecordPublic(
            uuid=record_uuid,
            id=record_id,
            steamid64=str(record_steamid64),
            player_name=player_name,
            player_avatar_hash=player_avatar_hash,
            steam_id=None,
            server_id=server_id,
            server_name=server_name or "",
            map_id=record_map_id,
            map_name=map_name,
            map_tier=tiers_by_course[(record_map_id, record_stage)],
            mode_id=record_mode_id,
            mode=mode_name,
            stage=record_stage,
            tickrate=128,
            time=float(record_time),
            teleports=record_teleports,
            points=points,
            created_on=created_on,
            updated_on=updated_on,
            updated_by=str(updated_by),
            replay_id=replay_id,
            is_valid=is_valid,
        )
        for (
            record_uuid,
            record_id,
            record_steamid64,
            player_name,
            player_avatar_hash,
            server_id,
            server_name,
            record_map_id,
            map_name,
            map_tier,
            record_mode_id,
            mode_name,
            record_stage,
            record_time,
            record_teleports,
            points,
            created_on,
            updated_on,
            updated_by,
            replay_id,
            is_valid,
        ) in rows
    ]


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
            statement = statement.order_by(
                col(Record.time).asc(),
                *_record_tie_breakers(),
            )
            statement = statement.offset(offset).limit(limit)
            return list((await session.exec(statement)).all())

    if resolved_map_id is not None or steamid64 is not None:
        records = await _get_pb_records_v0(
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
