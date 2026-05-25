import uuid
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import and_, bindparam, case, delete, exists, func, or_, text, true, update
from sqlalchemy.orm import aliased
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.regions import get_region_country_codes
from app.models import (
    Ban,
    Map,
    MapCourse,
    MapPbLeaderboardPublic,
    MapWrPublic,
    Mode,
    ModeScope,
    Player,
    PlayerFriend,
    RecentRecordCompatPublicV0,
    RecentRecordListQuery,
    RecentRecordMapPublic,
    RecentRecordModePublic,
    RecentRecordPublic,
    RecentRecordServerPublic,
    Record,
    RecordBulkDeleteCourse,
    RecordCompatPublicV0,
    RecordListQuery,
    RecordModerationAction,
    RecordModerationActionRecord,
    RecordModerationActionType,
    RecordPatch,
    RecordPb,
    RecordPublic,
    RecordType,
    ServerGlobalapi,
    ServerGlobalapiCompatPublicV0,
    TeleportsType,
    WorldRecordCountCompatPublicV0,
    generate_uuid7,
    get_datetime_utc,
    legacy_mode_id_to_kz_mode,
    mode_scope_from_id,
    mode_scope_modes,
    mode_scope_to_id,
    seconds_to_time_ms,
)
from app.services.course_points import (
    CoursePbEntry,
    calculate_bucket_points,
    calculate_estimated_pb_points,
)
from app.services.run_replay_storage import has_run_replay

from .ban import active_ban_exists_clause, not_active_ban_exists_clause
from .map import get_map_by_name
from .map_leaderboard import rebuild_map_leaderboards_for_keys
from .player import read_players_batch, to_player_ref_public
from .record_filter import load_scoped_course_tiers

RECENT_RECORD_NOTIFY_CHANNEL = "recent_record_updates"
RECENT_RECORD_EXACT_COUNT_THRESHOLD = 100_000

_record_pb_table = RecordPb.__table__

_RECORD_PB_POINTS_BULK_UPDATE = (
    update(_record_pb_table)
    .where(
        _record_pb_table.c.scope == bindparam("pk_scope"),
        _record_pb_table.c.course_id == bindparam("pk_course_id"),
        _record_pb_table.c.steamid64 == bindparam("pk_steamid64"),
        _record_pb_table.c.is_pro_only == bindparam("pk_type"),
    )
    .values(
        points=bindparam("next_points"),
        updated_at=bindparam("next_updated_on"),
    )
)


@dataclass(frozen=True, slots=True)
class _WinnerPbEntry:
    record_uuid: uuid.UUID
    time_ms: int
    created_at: datetime


def _course_pb_entry_for_record_time(
    *,
    record_uuid: uuid.UUID,
    time_seconds: Decimal,
) -> CoursePbEntry:
    return CoursePbEntry(
        record_uuid=record_uuid,
        time_ms=seconds_to_time_ms(time_seconds),
    )


def _record_tie_breakers() -> tuple:
    return (
        col(Record.id).asc().nullslast(),
        col(Record.uuid).asc(),
    )


def _serialize_record_snapshot(record: Record | None) -> dict[str, object] | None:
    if record is None:
        return None

    payload = record.model_dump(mode="json")
    for key, value in list(payload.items()):
        if isinstance(value, Enum):
            payload[key] = value.value
    return payload


def _not_active_ban_exists_split_clause(*, steamid64_column):
    # Split permanent and temporary bans so Postgres can use the ban index
    # selectively instead of hashing the full active-ban set.
    return and_(
        ~exists(
            select(Ban.id).where(
                col(Ban.steamid64) == steamid64_column,
                col(Ban.expires_on).is_(None),
            )
        ),
        ~exists(
            select(Ban.id).where(
                col(Ban.steamid64) == steamid64_column,
                col(Ban.expires_on) >= func.now(),
            )
        ),
    )


def _friend_or_self_clause(*, steamid64_column, viewer_steamid64: int):
    return or_(
        steamid64_column == viewer_steamid64,
        exists(
            select(PlayerFriend.friend_steamid64).where(
                col(PlayerFriend.player_steamid64) == viewer_steamid64,
                col(PlayerFriend.friend_steamid64) == steamid64_column,
            )
        ),
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


def _is_pro_only_from_record_type(record_type: RecordType) -> bool:
    return record_type is RecordType.PRO


def _record_pb_points_update_params(
    *,
    scope: int | ModeScope,
    course_id: int,
    steamid64: int,
    record_type: RecordType,
    points: int,
    updated_at: datetime,
) -> dict[str, object]:
    return {
        "pk_scope": scope if isinstance(scope, ModeScope) else mode_scope_from_id(scope),
        "pk_course_id": course_id,
        "pk_steamid64": steamid64,
        "pk_type": _is_pro_only_from_record_type(record_type),
        "next_points": points,
        "next_updated_on": updated_at,
    }


def _ordered_point_updates(
    updates: Sequence[tuple[dict[str, object], int, int]],
) -> list[dict[str, object]]:
    return [
        params
        for params, _current_points, _next_points in sorted(
            updates,
            key=lambda item: (
                item[1] == 1000 and item[2] != 1000,
                item[1] != 1000 and item[2] == 1000,
            ),
            reverse=True,
        )
    ]


def _stored_points_for_banned_record() -> int:
    return 1


def _expunge_loaded_record_pbs(*, session: AsyncSession) -> None:
    for instance in list(session.sync_session.identity_map.values()):
        if isinstance(instance, RecordPb):
            session.sync_session.expunge(instance)


async def _steamid64_has_active_ban(
    *,
    session: AsyncSession,
    steamid64: int,
) -> bool:
    statement = select(Ban.id).where(
        col(Ban.steamid64) == steamid64,
        or_(col(Ban.expires_on).is_(None), col(Ban.expires_on) >= func.now()),
    )
    return (await session.exec(statement.limit(1))).first() is not None


async def _load_active_banned_steamid64s(
    *,
    session: AsyncSession,
    steamid64s: Sequence[int],
) -> set[int]:
    if not steamid64s:
        return set()

    statement = select(Ban.steamid64).where(
        col(Ban.steamid64).in_(list(dict.fromkeys(steamid64s))),
        or_(col(Ban.expires_on).is_(None), col(Ban.expires_on) >= func.now()),
    )
    return set((await session.exec(statement)).all())


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


async def get_map_course_by_map_stage(
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
    scope: ModeScope,
) -> dict[uuid.UUID, int]:
    if not record_uuids:
        return {}

    statement = select(
        RecordPb.record_uuid,
        RecordPb.is_pro_only,
        case(
            (active_ban_exists_clause(steamid64_column=col(RecordPb.steamid64)), 0),
            else_=RecordPb.points,
        ).label("points"),
    ).where(
        col(RecordPb.record_uuid).in_(list(record_uuids)),
        col(RecordPb.scope) == scope,
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
    scope: ModeScope,
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
    scope: ModeScope,
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
) -> set[tuple[int, int, int, RecordType]]:
    if not is_valid:
        return set()

    keys = {
        (scope_id, course_id, steamid64, RecordType.NUB)
        for scope_id in scope_ids
    }
    if teleports == 0:
        keys |= {
            (scope_id, course_id, steamid64, RecordType.PRO)
            for scope_id in scope_ids
        }
    return keys


def _scope_ids_for_mode_id(mode_id: int) -> tuple[int, ...]:
    return tuple(
        mode_scope_to_id(scope)
        for scope in ModeScope
        if legacy_mode_id_to_kz_mode(mode_id) in mode_scope_modes(scope)
    )


async def _select_pb_winner(
    *,
    session: AsyncSession,
    scope_id: int,
    course_id: int,
    steamid64: int,
    record_type: RecordType,
) -> Record | None:
    course = await _get_map_course_by_id(session=session, course_id=course_id)
    if course is None:
        return None
    map_obj = await session.get(Map, course.map_id)
    if map_obj is None or not map_obj.validated:
        return None

    statement = (
        select(Record)
        .where(
            col(Record.is_valid) == true(),
            col(Record.steamid64) == steamid64,
            col(Record.map_id) == course.map_id,
            col(Record.stage) == course.stage,
            col(Record.mode).in_(list(mode_scope_modes(mode_scope_from_id(scope_id)))),
        )
        .order_by(col(Record.time).asc(), *_record_tie_breakers())
        .limit(1)
    )
    if record_type.is_pro:
        statement = statement.where(col(Record.teleports) == 0)

    return (await session.exec(statement)).first()


async def _load_bucket_course_tier(
    *,
    session: AsyncSession,
    course_id: int,
    scope_id: int,
) -> int:
    course = await _get_map_course_by_id(session=session, course_id=course_id)
    if course is None:
        raise ValueError(f"Unknown map course {course_id}")

    return (
        await load_scoped_course_tiers(
            session=session,
            course_keys=[(course.map_id, course.stage)],
            scope=mode_scope_from_id(scope_id),
        )
    )[(course.map_id, course.stage)]


async def _load_bucket_winner_entries(
    *,
    session: AsyncSession,
    course_id: int,
    scope_id: int,
    record_type: RecordType,
) -> list[tuple[int, _WinnerPbEntry]]:
    course = await _get_map_course_by_id(session=session, course_id=course_id)
    if course is None:
        return []

    map_obj = await session.get(Map, course.map_id)
    if map_obj is None or not map_obj.validated:
        return []

    winner_rows = select(
        Record.steamid64.label("steamid64"),
        Record.uuid.label("record_uuid"),
        Record.time.label("time_seconds"),
        Record.created_at.label("created_at"),
        Record.id.label("record_id"),
    ).where(
        col(Record.is_valid).is_(True),
        col(Record.map_id) == course.map_id,
        col(Record.stage) == course.stage,
        col(Record.mode).in_(list(mode_scope_modes(mode_scope_from_id(scope_id)))),
    )
    if record_type.is_pro:
        winner_rows = winner_rows.where(col(Record.teleports) == 0)

    winner_rows = winner_rows.distinct(col(Record.steamid64)).order_by(
        col(Record.steamid64).asc(),
        col(Record.time).asc(),
        *_record_tie_breakers(),
    )
    winner_rows_subquery = winner_rows.subquery()

    ordered_winners = (
        await session.exec(
            select(
                winner_rows_subquery.c.steamid64,
                winner_rows_subquery.c.record_uuid,
                winner_rows_subquery.c.time_seconds,
                winner_rows_subquery.c.created_at,
                winner_rows_subquery.c.record_id,
            ).order_by(
                winner_rows_subquery.c.time_seconds.asc(),
                winner_rows_subquery.c.record_id.asc().nullslast(),
                winner_rows_subquery.c.record_uuid.asc(),
            )
        )
    ).all()
    return [
        (
            steamid64,
            _WinnerPbEntry(
                record_uuid=record_uuid,
                time_ms=seconds_to_time_ms(time_seconds),
                created_at=created_at,
            ),
        )
        for steamid64, record_uuid, time_seconds, created_at, _record_id in ordered_winners
    ]


async def _load_bucket_record_pb_entries(
    *,
    session: AsyncSession,
    course_id: int,
    scope_id: int,
    record_type: RecordType,
    exclude_steamid64: int | None = None,
) -> list[CoursePbEntry]:
    statement = (
        select(RecordPb.record_uuid, Record.time)
        .join(Record, Record.uuid == RecordPb.record_uuid)
        .where(
            col(RecordPb.scope) == mode_scope_from_id(scope_id),
            col(RecordPb.course_id) == course_id,
            col(RecordPb.is_pro_only).is_(_is_pro_only_from_record_type(record_type)),
            _not_active_ban_exists_split_clause(
                steamid64_column=col(RecordPb.steamid64)
            ),
        )
        .order_by(col(Record.time).asc(), col(Record.uuid).asc())
    )
    if exclude_steamid64 is not None:
        statement = statement.where(col(RecordPb.steamid64) != exclude_steamid64)

    return [
        _course_pb_entry_for_record_time(
            record_uuid=record_uuid,
            time_seconds=time_seconds,
        )
        for record_uuid, time_seconds in (await session.exec(statement)).all()
    ]


async def _estimate_record_pb_points(
    *,
    session: AsyncSession,
    course_id: int,
    scope_id: int,
    steamid64: int,
    record_type: RecordType,
    record_uuid: uuid.UUID,
    time_ms: int,
) -> int:
    if await _steamid64_has_active_ban(session=session, steamid64=steamid64):
        return _stored_points_for_banned_record()

    tier = await _load_bucket_course_tier(
        session=session,
        course_id=course_id,
        scope_id=scope_id,
    )
    entries = await _load_bucket_record_pb_entries(
        session=session,
        course_id=course_id,
        scope_id=scope_id,
        record_type=record_type,
        exclude_steamid64=steamid64,
    )
    entries.append(CoursePbEntry(record_uuid=record_uuid, time_ms=time_ms))
    entries.sort(key=lambda entry: (entry.time_ms, entry.record_uuid))
    return calculate_estimated_pb_points(
        winner_record_uuid=record_uuid,
        entries=entries,
        tier=tier,
        is_pro_only=record_type.is_pro,
    )


async def _sync_record_pb_bucket(
    *,
    session: AsyncSession,
    course_id: int,
    scope_id: int,
    record_type: RecordType,
    time_changed_record_uuids: set[uuid.UUID] | None = None,
) -> None:
    existing_rows = (
        await session.exec(
            select(RecordPb).where(
                col(RecordPb.scope) == mode_scope_from_id(scope_id),
                col(RecordPb.course_id) == course_id,
                col(RecordPb.is_pro_only).is_(_is_pro_only_from_record_type(record_type)),
            )
        )
    ).all()
    existing_by_steamid64 = {
        row.steamid64: row
        for row in existing_rows
    }

    winner_entries = await _load_bucket_winner_entries(
        session=session,
        course_id=course_id,
        scope_id=scope_id,
        record_type=record_type,
    )
    winner_by_steamid64 = dict(winner_entries)

    for steamid64, existing in existing_by_steamid64.items():
        if steamid64 not in winner_by_steamid64:
            await session.delete(existing)

    for steamid64, winner in winner_by_steamid64.items():
        existing = existing_by_steamid64.get(steamid64)
        if existing is not None:
            if (
                existing.record_uuid == winner.record_uuid
                and winner.record_uuid not in (time_changed_record_uuids or set())
            ):
                continue
            existing.record_uuid = winner.record_uuid
            existing.updated_at = get_datetime_utc()
            if existing.points < 1:
                existing.points = 1
            session.add(existing)
            continue

        session.add(
            RecordPb(
                scope=mode_scope_from_id(scope_id),
                course_id=course_id,
                steamid64=steamid64,
                is_pro_only=_is_pro_only_from_record_type(record_type),
                record_uuid=winner.record_uuid,
                points=1,
                updated_at=winner.created_at,
            )
        )


async def _sync_record_pb_key(
    *,
    session: AsyncSession,
    scope_id: int,
    course_id: int,
    steamid64: int,
    record_type: RecordType,
    time_changed_record_uuids: set[uuid.UUID] | None = None,
) -> None:
    existing = await session.get(
        RecordPb,
        (
            mode_scope_from_id(scope_id),
            course_id,
            steamid64,
            _is_pro_only_from_record_type(record_type),
        ),
    )
    winner = await _select_pb_winner(
        session=session,
        scope_id=scope_id,
        course_id=course_id,
        steamid64=steamid64,
        record_type=record_type,
    )

    if winner is None:
        if existing is not None:
            await session.delete(existing)
        return

    time_ms = seconds_to_time_ms(winner.time)
    if (
        existing is not None
        and existing.record_uuid == winner.uuid
        and winner.uuid not in (time_changed_record_uuids or set())
    ):
        return

    estimated_points = await _estimate_record_pb_points(
        session=session,
        course_id=course_id,
        scope_id=scope_id,
        steamid64=steamid64,
        record_type=record_type,
        record_uuid=winner.uuid,
        time_ms=time_ms,
    )
    if existing is not None:
        existing.record_uuid = winner.uuid
        existing.points = estimated_points
        existing.updated_at = get_datetime_utc()
        session.add(existing)
        return

    session.add(
        RecordPb(
            scope=mode_scope_from_id(scope_id),
            course_id=course_id,
            steamid64=steamid64,
            is_pro_only=_is_pro_only_from_record_type(record_type),
            record_uuid=winner.uuid,
            points=estimated_points,
            updated_at=winner.created_at,
        )
    )


async def rebuild_record_pb_points_bucket(
    *,
    session: AsyncSession,
    course_id: int,
    scope_id: int,
    record_type: RecordType,
    tier: int | None = None,
) -> int:
    rows = (
        await session.exec(
            select(
                RecordPb.scope,
                RecordPb.course_id,
                RecordPb.steamid64,
                RecordPb.is_pro_only,
                RecordPb.record_uuid,
                Record.time,
                RecordPb.points,
                RecordPb.updated_at,
            )
            .join(Record, Record.uuid == RecordPb.record_uuid)
            .where(
                col(RecordPb.scope) == mode_scope_from_id(scope_id),
                col(RecordPb.course_id) == course_id,
                col(RecordPb.is_pro_only).is_(_is_pro_only_from_record_type(record_type)),
            )
            .order_by(col(Record.time).asc(), col(Record.uuid).asc())
        )
    ).all()
    if not rows:
        return 0

    banned_steamid64s = await _load_active_banned_steamid64s(
        session=session,
        steamid64s=[steamid64 for _scope, _course, steamid64, *_rest in rows],
    )

    resolved_tier = (
        tier
        if tier is not None
        else await _load_bucket_course_tier(
            session=session,
            course_id=course_id,
            scope_id=scope_id,
        )
    )
    points_by_uuid = calculate_bucket_points(
        entries=[
            _course_pb_entry_for_record_time(
                record_uuid=record_uuid,
                time_seconds=time_seconds,
            )
            for (
                _row_scope_id,
                _row_course_id,
                steamid64,
                _row_record_type,
                record_uuid,
                time_seconds,
                _current_points,
                _row_updated_on,
            ) in rows
            if steamid64 not in banned_steamid64s
        ],
        tier=resolved_tier,
        is_pro_only=record_type.is_pro,
    )
    updates = _ordered_point_updates(
        [
            (
                _record_pb_points_update_params(
                    scope=row_scope_id,
                    course_id=row_course_id,
                    steamid64=steamid64,
                    record_type=RecordType.PRO if row_record_type else RecordType.NUB,
                    points=(
                        _stored_points_for_banned_record()
                        if steamid64 in banned_steamid64s
                        else points_by_uuid[record_uuid]
                    ),
                    updated_at=row_updated_on,
                ),
                current_points,
                _stored_points_for_banned_record()
                if steamid64 in banned_steamid64s
                else points_by_uuid[record_uuid],
            )
            for (
                row_scope_id,
                row_course_id,
                steamid64,
                row_record_type,
                record_uuid,
                _time_seconds,
                current_points,
                row_updated_on,
            ) in rows
            if current_points
            != (
                _stored_points_for_banned_record()
                if steamid64 in banned_steamid64s
                else points_by_uuid[record_uuid]
            )
        ]
    )
    if updates:
        await session.execute(_RECORD_PB_POINTS_BULK_UPDATE, updates)
        _expunge_loaded_record_pbs(session=session)
    return len(updates)


async def rebuild_record_pb_points_for_course(
    *,
    session: AsyncSession,
    course_id: int,
    scope_ids: Sequence[int] | None = None,
    tiers_by_scope: Mapping[int, int] | None = None,
) -> int:
    statement = (
        select(
            RecordPb.scope,
            RecordPb.course_id,
            RecordPb.steamid64,
            RecordPb.is_pro_only,
            RecordPb.record_uuid,
            Record.time,
            RecordPb.points,
            RecordPb.updated_at,
        )
        .join(Record, Record.uuid == RecordPb.record_uuid)
        .where(col(RecordPb.course_id) == course_id)
        .order_by(
            col(RecordPb.scope).asc(),
            col(RecordPb.is_pro_only).asc(),
            col(Record.time).asc(),
            col(Record.uuid).asc(),
        )
    )
    if scope_ids is not None:
        statement = statement.where(
            col(RecordPb.scope).in_([mode_scope_from_id(scope_id) for scope_id in scope_ids])
        )

    rows = (await session.exec(statement)).all()
    if not rows:
        return 0

    normalized_tiers = dict(tiers_by_scope or {})
    grouped_rows: dict[
        tuple[ModeScope, bool],
        list[tuple[ModeScope, int, int, bool, uuid.UUID, Decimal, int, datetime]],
    ] = defaultdict(list)
    for row in rows:
        grouped_rows[(row[0], row[3])].append(row)

    missing_scope_ids = sorted(
        {
            scope.scope_id
            for scope, _ in grouped_rows
            if scope.scope_id not in normalized_tiers
        }
    )
    if missing_scope_ids:
        course = await _get_map_course_by_id(session=session, course_id=course_id)
        if course is None:
            raise ValueError(f"Unknown map course {course_id}")

        course_key = (course.map_id, course.stage)
        for missing_scope_id in missing_scope_ids:
            normalized_tiers[missing_scope_id] = (
                await load_scoped_course_tiers(
                    session=session,
                    course_keys=[course_key],
                    scope=mode_scope_from_id(missing_scope_id),
                )
            )[course_key]

    raw_updates: list[tuple[dict[str, object], int, int]] = []
    for (scope, is_pro_only), bucket_rows in grouped_rows.items():
        points_by_uuid = calculate_bucket_points(
            entries=[
                _course_pb_entry_for_record_time(
                    record_uuid=record_uuid,
                    time_seconds=time_seconds,
                )
                for (
                    _row_scope_id,
                    _row_course_id,
                    _steamid64,
                    _row_record_type,
                    record_uuid,
                    time_seconds,
                    _current_points,
                    _row_updated_on,
                ) in bucket_rows
            ],
            tier=normalized_tiers[scope.scope_id],
            is_pro_only=is_pro_only,
        )
        raw_updates.extend(
            (
                _record_pb_points_update_params(
                    scope=row_scope_id,
                    course_id=row_course_id,
                    steamid64=steamid64,
                    record_type=RecordType.PRO if row_record_type else RecordType.NUB,
                    points=points_by_uuid[record_uuid],
                    updated_at=row_updated_on,
                ),
                current_points,
                points_by_uuid[record_uuid],
            )
            for (
                row_scope_id,
                row_course_id,
                steamid64,
                row_record_type,
                record_uuid,
                _time_seconds,
                current_points,
                row_updated_on,
            ) in bucket_rows
            if current_points != points_by_uuid[record_uuid]
        )

    updates = _ordered_point_updates(raw_updates)
    if updates:
        await session.execute(_RECORD_PB_POINTS_BULK_UPDATE, updates)
        _expunge_loaded_record_pbs(session=session)
    return len(updates)


async def recompute_record_pbs_for_keys(
    *,
    session: AsyncSession,
    keys: set[tuple[int, int, int, RecordType]],
    time_changed_record_uuids: set[uuid.UUID] | None = None,
) -> None:
    for scope_id, course_id, steamid64, record_type in keys:
        await _sync_record_pb_key(
            session=session,
            scope_id=scope_id,
            course_id=course_id,
            steamid64=steamid64,
            record_type=record_type,
            time_changed_record_uuids=time_changed_record_uuids,
        )


async def rebuild_record_pb_buckets_for_keys(
    *,
    session: AsyncSession,
    keys: set[tuple[int, int, int, RecordType]],
    time_changed_record_uuids: set[uuid.UUID] | None = None,
) -> None:
    bucket_keys = sorted(
        {
            (scope_id, course_id, record_type)
            for scope_id, course_id, _steamid64, record_type in keys
        }
    )
    for scope_id, course_id, record_type in bucket_keys:
        await _sync_record_pb_bucket(
            session=session,
            course_id=course_id,
            scope_id=scope_id,
            record_type=record_type,
            time_changed_record_uuids=time_changed_record_uuids,
        )
        await rebuild_record_pb_points_bucket(
            session=session,
            course_id=course_id,
            scope_id=scope_id,
            record_type=record_type,
        )


async def rebuild_record_pbs(*, session: AsyncSession) -> None:
    await ensure_map_courses_for_valid_records(session=session)
    courses = (
        await session.exec(
            select(MapCourse)
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


async def ensure_map_courses_for_exact_record_filters(*, session: AsyncSession) -> None:
    await session.exec(
        text(
            """
            INSERT INTO map_course (map_id, stage)
            SELECT DISTINCT record_filter.map_id, record_filter.stage
            FROM record_filter
            JOIN map
              ON map.id = record_filter.map_id
            WHERE record_filter.map_id > 0
              AND record_filter.tickrate = 128
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
    del map_id, stage
    for scope in ModeScope:
        scope_id = mode_scope_to_id(scope)
        for record_type in RecordType:
            await _sync_record_pb_bucket(
                session=session,
                course_id=course_id,
                scope_id=scope_id,
                record_type=record_type,
            )
            await rebuild_record_pb_points_bucket(
                session=session,
                course_id=course_id,
                scope_id=scope_id,
                record_type=record_type,
            )


async def read_map_wrs(
    *,
    session: AsyncSession,
    map_id: int | None,
    scope: ModeScope,
    record_type: RecordType | None = None,
) -> list[MapWrPublic]:
    statement = (
        select(
            MapCourse.map_id,
            RecordPb.scope,
            RecordPb.is_pro_only,
            RecordPb.record_uuid,
            RecordPb.updated_at,
            Record.mode,
            Record.steamid64,
            Record.time,
        )
        .join(MapCourse, MapCourse.id == RecordPb.course_id)
        .join(Map, Map.id == MapCourse.map_id)
        .join(Record, Record.uuid == RecordPb.record_uuid)
        .where(
            RecordPb.scope == scope,
            RecordPb.points == 1000,
            MapCourse.stage == 0,
            Map.validated.is_(True),
        )
        .order_by(RecordPb.is_pro_only.asc(), MapCourse.map_id.asc())
    )
    if map_id is not None:
        statement = statement.where(MapCourse.map_id == map_id)
    if record_type is not None:
        statement = statement.where(
            RecordPb.is_pro_only.is_(_is_pro_only_from_record_type(record_type))
        )

    rows = (await session.exec(statement)).all()
    unique_steamid64s = list(dict.fromkeys(row[6] for row in rows))
    players = await read_players_batch(session=session, steamid64s=unique_steamid64s)
    players_by_steamid64 = {
        player.steamid64: player for player in players if player is not None
    }

    return [
        MapWrPublic(
            record_uuid=record_uuid,
            map_id=row_map_id,
            scope=row_scope,
            type=RecordType.PRO if row_is_pro_only else RecordType.NUB,
            mode_id=mode.mode_id,
            player=to_player_ref_public(player=players_by_steamid64[player_steamid64]),
            time=float(record_time),
            updated_at=updated_at,
        )
        for (
            row_map_id,
            row_scope,
            row_is_pro_only,
            record_uuid,
            updated_at,
            mode,
            player_steamid64,
            record_time,
        ) in rows
    ]


async def _pb_keys_for_record_snapshot(
    *,
    session: AsyncSession,
    map_id: int,
    stage: int,
    mode_id: int,
    steamid64: int,
    teleports: int,
    is_valid: bool,
) -> set[tuple[int, int, int, RecordType]]:
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


def _map_leaderboard_keys_for_record_snapshot(
    *,
    map_id: int,
    stage: int,
    mode_id: int,
) -> set[tuple[int, int]]:
    if stage != 0 or map_id <= 0:
        return set()

    return {
        (map_id, scope_id)
        for scope_id in _scope_ids_for_mode_id(mode_id)
    }


async def _refresh_record_read_models_for_change(
    *,
    session: AsyncSession,
    before: Record | None,
    after: Record | None,
) -> None:
    pb_keys: set[tuple[int, int, int, RecordType]] = set()
    map_leaderboard_keys: set[tuple[int, int]] = set()
    time_changed_record_uuids: set[uuid.UUID] = set()
    if before is not None:
        pb_keys |= await _pb_keys_for_record_snapshot(
            session=session,
            map_id=before.map_id,
            stage=before.stage,
            mode_id=before.mode_id,
            steamid64=before.steamid64,
            teleports=before.teleports,
            is_valid=before.is_valid,
        )
        map_leaderboard_keys |= _map_leaderboard_keys_for_record_snapshot(
            map_id=before.map_id,
            stage=before.stage,
            mode_id=before.mode_id,
        )
    if after is not None:
        pb_keys |= await _pb_keys_for_record_snapshot(
            session=session,
            map_id=after.map_id,
            stage=after.stage,
            mode_id=after.mode_id,
            steamid64=after.steamid64,
            teleports=after.teleports,
            is_valid=after.is_valid,
        )
        map_leaderboard_keys |= _map_leaderboard_keys_for_record_snapshot(
            map_id=after.map_id,
            stage=after.stage,
            mode_id=after.mode_id,
        )
    if before is not None and after is not None and before.uuid == after.uuid:
        if before.time != after.time:
            time_changed_record_uuids.add(after.uuid)

    await rebuild_record_pb_buckets_for_keys(
        session=session,
        keys=pb_keys,
        time_changed_record_uuids=time_changed_record_uuids,
    )
    await rebuild_map_leaderboards_for_keys(
        session=session,
        keys=sorted(map_leaderboard_keys),
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
    mode = (
        await session.exec(select(Mode).where(col(Mode.name_short) == record.mode).limit(1))
    ).first()
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
        player=to_player_ref_public(player=player),
        steam_id=None,
        server_id=record.server_id,
        server_name=server.name or "",
        map_id=record.map_id,
        map_name=map_obj.name,
        map_tier=map_tier,
        mode_id=record.mode_id,
        mode=mode.name_short.value,
        stage=record.stage,
        tickrate=128,
        time=float(record.time),
        teleports=record.teleports,
        points=points,
        created_on=record.created_at,
        updated_on=record.updated_at,
        updated_by=str(record.updated_by),
        replay_id=record.replay_id,
        is_replay_available=has_run_replay(
            map_name=map_obj.name,
            replay_id=record.uuid,
        ),
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
        player=to_player_ref_public(player=player),
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
            name=mode.name_short.value,
        ),
        stage=record.stage,
        teleports=record.teleports,
        time=float(record.time),
        points=points,
        created_on=record.created_at,
        updated_on=record.updated_at,
        is_replay_available=has_run_replay(
            map_name=map_obj.name,
            replay_id=record.uuid,
        ),
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
        created_on=record.created_at,
        updated_on=record.updated_at,
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
        filters.append(col(Record.mode) == legacy_mode_id_to_kz_mode(query.mode_id))
    if query.map_id is not None:
        filters.append(col(Record.map_id) == query.map_id)
    elif query.map_name is not None:
        filters.append(
            col(Record.map_id).in_(
                select(Map.id).where(col(Map.name) == query.map_name)
            )
        )
    if query.stage is not None:
        filters.append(col(Record.stage) == query.stage)
    if query.teleports is not None:
        filters.append(col(Record.teleports) == query.teleports)
    if query.replay_id is not None:
        filters.append(col(Record.replay_id) == query.replay_id)
    if query.is_valid is not None:
        filters.append(col(Record.is_valid) == query.is_valid)
    if query.created_since is not None:
        filters.append(col(Record.created_at) >= query.created_since)
    if query.updated_since is not None:
        filters.append(col(Record.updated_at) >= query.updated_since)
    if query.exclude_cheaters:
        filters.append(
            not_active_ban_exists_clause(steamid64_column=col(Record.steamid64))
        )

    count_statement = select(func.count()).select_from(Record)
    statement = select(Record)
    for condition in filters:
        count_statement = count_statement.where(condition)
        statement = statement.where(condition)

    count = (await session.exec(count_statement)).one()
    statement = (
        statement.order_by(col(Record.created_at).desc(), col(Record.uuid).desc())
        .offset(query.offset)
        .limit(query.limit)
    )
    records = list((await session.exec(statement)).all())
    return records, count


async def read_records_with_replays(
    *,
    session: AsyncSession,
    record_uuids: Sequence[uuid.UUID],
    scope: ModeScope,
    exclude_cheaters: bool,
) -> list[RecordPublic]:
    unique_record_uuids = list(dict.fromkeys(record_uuids))
    if not unique_record_uuids:
        return []

    statement = (
        select(Record, Player, ServerGlobalapi, Map, Mode)
        .join(Player, col(Record.steamid64) == col(Player.steamid64))
        .join(ServerGlobalapi, col(Record.server_id) == col(ServerGlobalapi.id))
        .join(Map, col(Record.map_id) == col(Map.id))
        .join(Mode, col(Record.mode) == col(Mode.name_short))
        .where(col(Record.uuid).in_(unique_record_uuids))
    )
    if exclude_cheaters:
        statement = statement.where(
            not_active_ban_exists_clause(steamid64_column=col(Record.steamid64))
        )

    rows = list((await session.exec(statement)).all())
    if not rows:
        return []

    points_by_uuid = await _load_pb_points_by_record_uuid(
        session=session,
        record_uuids=[record.uuid for record, *_rest in rows],
        scope=scope,
    )
    tiers_by_course = await _load_scoped_record_tiers(
        session=session,
        record_courses=[(record.map_id, record.stage) for record, *_rest in rows],
        scope=scope,
    )
    publics_by_uuid = {
        record.uuid: to_record_public(
            record=record,
            player=player,
            server=server,
            map_obj=map_obj,
            mode=mode,
            map_tier=tiers_by_course[(record.map_id, record.stage)],
            points=points_by_uuid.get(record.uuid, 0),
        )
        for record, player, server, map_obj, mode in rows
    }
    return [
        publics_by_uuid[record_uuid]
        for record_uuid in unique_record_uuids
        if record_uuid in publics_by_uuid
    ]


async def read_recent_records(
    *,
    session: AsyncSession,
    query: RecentRecordListQuery,
) -> tuple[list[RecentRecordPublic], int]:
    pro_pb = aliased(RecordPb)
    ovr_pb = aliased(RecordPb)
    requested_record_type = query.type
    if requested_record_type is RecordType.PRO:
        scoped_points = func.coalesce(pro_pb.points, 0)
    elif requested_record_type is RecordType.NUB:
        scoped_points = func.coalesce(ovr_pb.points, 0)
    else:
        scoped_points = func.coalesce(pro_pb.points, ovr_pb.points, 0)
    public_scoped_points = case(
        (active_ban_exists_clause(steamid64_column=col(Record.steamid64)), 0),
        else_=scoped_points,
    )

    statement = (
        select(
            Record,
            Player,
            ServerGlobalapi,
            Map,
            Mode,
            public_scoped_points.label("points"),
        )
        .join(Player, col(Record.steamid64) == col(Player.steamid64))
        .join(ServerGlobalapi, col(Record.server_id) == col(ServerGlobalapi.id))
        .join(Map, col(Record.map_id) == col(Map.id))
        .join(Mode, col(Record.mode) == col(Mode.name_short))
        .outerjoin(
            pro_pb,
            and_(
                pro_pb.record_uuid == Record.uuid,
                pro_pb.scope == query.scope,
                pro_pb.is_pro_only.is_(True),
            ),
        )
        .outerjoin(
            ovr_pb,
            and_(
                ovr_pb.record_uuid == Record.uuid,
                ovr_pb.scope == query.scope,
                ovr_pb.is_pro_only.is_(False),
            ),
        )
        .where(col(Record.is_valid).is_(True))
    )
    if requested_record_type is RecordType.PRO or query.is_pro_only is True:
        statement = statement.where(col(Record.teleports) == 0)
    elif requested_record_type is RecordType.NUB:
        statement = statement.where(col(Record.teleports) > 0)
    if query.points_more_or_equal_than is not None:
        statement = statement.where(
            public_scoped_points >= query.points_more_or_equal_than
        )

    if (
        query.points_more_or_equal_than is None
        and query.is_pro_only is not True
        and requested_record_type is None
    ):
        count = await _estimate_record_count(session=session, is_valid=True)
    else:
        count_statement = (
            select(func.count())
            .select_from(Record)
            .outerjoin(
                pro_pb,
                and_(
                    pro_pb.record_uuid == Record.uuid,
                    pro_pb.scope == query.scope,
                    pro_pb.is_pro_only.is_(True),
                ),
            )
            .outerjoin(
                ovr_pb,
                and_(
                    ovr_pb.record_uuid == Record.uuid,
                    ovr_pb.scope == query.scope,
                    ovr_pb.is_pro_only.is_(False),
                ),
            )
            .where(col(Record.is_valid).is_(True))
        )
        if requested_record_type is RecordType.PRO or query.is_pro_only is True:
            count_statement = count_statement.where(col(Record.teleports) == 0)
        elif requested_record_type is RecordType.NUB:
            count_statement = count_statement.where(col(Record.teleports) > 0)
        if query.points_more_or_equal_than is not None:
            count_statement = count_statement.where(
                public_scoped_points >= query.points_more_or_equal_than
            )
        count = (await session.exec(count_statement)).one()

    rows = (
        await session.exec(
            statement.order_by(
                col(Record.created_at).desc(),
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
    scope: ModeScope = ModeScope.OVR,
) -> RecentRecordPublic | None:
    statement = (
        select(Record, Player, ServerGlobalapi, Map, Mode)
        .join(Player, col(Record.steamid64) == col(Player.steamid64))
        .join(ServerGlobalapi, col(Record.server_id) == col(ServerGlobalapi.id))
        .join(Map, col(Record.map_id) == col(Map.id))
        .join(Mode, col(Record.mode) == col(Mode.name_short))
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
            mode=legacy_mode_id_to_kz_mode(mode_id),
            map_id=map_id,
            stage=stage,
            time=time_seconds,
            teleports=teleports,
            points=points,
            created_at=created_on,
            updated_at=updated_on,
            updated_by=updated_by,
            replay_id=replay_id,
            is_valid=is_valid,
        )
        session.add(record)
        await _refresh_record_read_models_for_change(
            session=session,
            before=None,
            after=record,
        )
        return record, True, False

    before_record = Record.model_validate(existing_record.model_dump())
    existing_record.steamid64 = steamid64
    existing_record.server_id = server_id
    existing_record.mode = legacy_mode_id_to_kz_mode(mode_id)
    existing_record.map_id = map_id
    existing_record.stage = stage
    existing_record.time = time_seconds
    existing_record.teleports = teleports
    existing_record.points = points
    existing_record.created_at = created_on
    existing_record.updated_at = updated_on
    existing_record.updated_by = updated_by
    existing_record.replay_id = replay_id
    existing_record.is_valid = is_valid
    session.add(existing_record)
    await _refresh_record_read_models_for_change(
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
    actor_steamid64: int,
) -> Record:
    before_record = Record.model_validate(record.model_dump())
    record.is_valid = patch.is_valid
    record.updated_at = get_datetime_utc()
    session.add(record)
    await _refresh_record_read_models_for_change(
        session=session,
        before=before_record,
        after=record,
    )
    action = RecordModerationAction(
        actor_steamid64=actor_steamid64,
        action_type=(
            RecordModerationActionType.SINGLE_REENABLE
            if patch.is_valid
            else RecordModerationActionType.SINGLE_SOFT_DELETE
        ),
        target_record_uuid=record.uuid,
        target_player_steamid64=record.steamid64,
        target_map_id=record.map_id,
        target_stage=record.stage,
    )
    session.add(action)
    await session.flush()
    session.add(
        RecordModerationActionRecord(
            action_id=action.id,
            record_uuid=record.uuid,
            record_id=record.id,
            player_steamid64=record.steamid64,
            map_id=record.map_id,
            stage=record.stage,
            before_snapshot=_serialize_record_snapshot(before_record),
            after_snapshot=_serialize_record_snapshot(record),
        )
    )
    await session.commit()
    await session.refresh(record)
    return record


async def bulk_soft_delete_course_records(
    *,
    session: AsyncSession,
    payload: RecordBulkDeleteCourse,
    actor_steamid64: int,
) -> list[Record]:
    target_steamid64 = int(payload.steamid64)
    statement = (
        select(Record)
        .where(
            col(Record.steamid64) == target_steamid64,
            col(Record.map_id) == payload.map_id,
            col(Record.stage) == payload.stage,
            col(Record.is_valid).is_(True),
        )
        .order_by(*_record_tie_breakers())
    )
    records = list((await session.exec(statement)).all())
    if not records:
        return []

    before_records = [Record.model_validate(record.model_dump()) for record in records]
    changed_at = get_datetime_utc()
    action = RecordModerationAction(
        actor_steamid64=actor_steamid64,
        action_type=RecordModerationActionType.BULK_SOFT_DELETE_COURSE,
        target_player_steamid64=target_steamid64,
        target_map_id=payload.map_id,
        target_stage=payload.stage,
    )
    session.add(action)
    await session.flush()

    course = await get_map_course_by_map_stage(
        session=session,
        map_id=payload.map_id,
        stage=payload.stage,
    )
    if course is not None:
        await session.exec(
            delete(RecordPb).where(
                col(RecordPb.course_id) == course.id,
                col(RecordPb.steamid64) == target_steamid64,
            )
        )
        _expunge_loaded_record_pbs(session=session)

    for before_record, record in zip(before_records, records, strict=True):
        record.is_valid = False
        record.updated_at = changed_at
        session.add(record)
        session.add(
            RecordModerationActionRecord(
                action_id=action.id,
                record_uuid=record.uuid,
                record_id=record.id,
                player_steamid64=record.steamid64,
                map_id=record.map_id,
                stage=record.stage,
                before_snapshot=_serialize_record_snapshot(before_record),
                after_snapshot=_serialize_record_snapshot(record),
            )
        )

    await session.commit()
    return records


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
    exclude_cheaters: bool,
) -> list[Record]:
    statement = select(Record).where(col(Record.is_valid).is_(True))
    if mode_ids:
        statement = statement.where(
            col(Record.mode).in_([legacy_mode_id_to_kz_mode(mode_id) for mode_id in mode_ids])
        )
    if server_ids:
        statement = statement.where(col(Record.server_id).in_(list(server_ids)))
    if exclude_cheaters:
        statement = statement.where(
            not_active_ban_exists_clause(steamid64_column=col(Record.steamid64))
        )

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
    scope: ModeScope,
    record_type: RecordType,
    exclude_cheaters: bool = True,
    offset: int = 0,
    limit: int = 100,
) -> list[Record]:
    if map_id is not None:
        course = await get_map_course_by_map_stage(
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
                RecordPb.scope == scope,
                RecordPb.course_id == course.id,
                RecordPb.is_pro_only.is_(_is_pro_only_from_record_type(record_type)),
            )
            .order_by(Record.time.asc(), Record.uuid.asc())
            .offset(offset)
            .limit(limit)
        )
        if steamid64 is not None:
            statement = statement.where(RecordPb.steamid64 == steamid64)
        if exclude_cheaters:
            statement = statement.where(
                not_active_ban_exists_clause(steamid64_column=col(Record.steamid64))
            )
        return list((await session.exec(statement)).all())

    if steamid64 is not None:
        course = aliased(MapCourse)
        statement = (
            select(Record)
            .join(RecordPb, RecordPb.record_uuid == Record.uuid)
            .join(course, course.id == RecordPb.course_id)
            .where(
                RecordPb.scope == scope,
                RecordPb.steamid64 == steamid64,
                RecordPb.is_pro_only.is_(_is_pro_only_from_record_type(record_type)),
                course.stage == stage,
            )
            .order_by(
                course.map_id.asc(),
                course.stage.asc(),
                Record.time.asc(),
                Record.uuid.asc(),
            )
            .offset(offset)
            .limit(limit)
        )
        if exclude_cheaters:
            statement = statement.where(
                not_active_ban_exists_clause(steamid64_column=col(Record.steamid64))
            )
        return list((await session.exec(statement)).all())

    return []


async def get_pb_record_publics(
    session: AsyncSession,
    *,
    map_id: int | None,
    map_name: str | None,
    stage: int,
    steamid64: int | None,
    scope: ModeScope,
    record_type: RecordType,
    country: str | None = None,
    region: str | None = None,
    exclude_cheaters: bool = True,
    offset: int = 0,
    limit: int = 100,
) -> list[RecordPublic]:
    anchor_pb = aliased(RecordPb)
    pro_pb = aliased(RecordPb)
    ovr_pb = aliased(RecordPb)
    scoped_points = (
        pro_pb.points if record_type.is_pro else func.coalesce(ovr_pb.points, 0)
    )
    public_scoped_points = case(
        (active_ban_exists_clause(steamid64_column=col(Record.steamid64)), 0),
        else_=scoped_points,
    )

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
            Record.mode,
            Mode.name_short,
            Record.stage,
            Record.time,
            Record.teleports,
            public_scoped_points.label("points"),
            Record.created_at,
            Record.updated_at,
            Record.updated_by,
            Record.replay_id,
            Record.is_valid,
        )
        .join(anchor_pb, anchor_pb.record_uuid == Record.uuid)
        .join(Player, col(Record.steamid64) == col(Player.steamid64))
        .join(ServerGlobalapi, col(Record.server_id) == col(ServerGlobalapi.id))
        .join(Map, col(Record.map_id) == col(Map.id))
        .join(Mode, col(Record.mode) == col(Mode.name_short))
        .outerjoin(
            pro_pb,
            and_(
                pro_pb.record_uuid == Record.uuid,
                pro_pb.scope == scope,
                pro_pb.is_pro_only.is_(True),
            ),
        )
        .outerjoin(
            ovr_pb,
            and_(
                ovr_pb.record_uuid == Record.uuid,
                ovr_pb.scope == scope,
                ovr_pb.is_pro_only.is_(False),
            ),
        )
    )
    geography_country_codes = (
        (country,) if country is not None else get_region_country_codes(region)
    )
    if geography_country_codes is not None:
        statement = statement.where(col(Player.country).in_(list(geography_country_codes)))
    if exclude_cheaters:
        statement = statement.where(
            not_active_ban_exists_clause(steamid64_column=col(Record.steamid64))
        )

    resolved_map_id = map_id
    if resolved_map_id is None and map_name is not None:
        map_obj = await get_map_by_name(session=session, map_name=map_name)
        if map_obj is None:
            return []
        resolved_map_id = map_obj.id

    if resolved_map_id is not None:
        course = await get_map_course_by_map_stage(
            session=session,
            map_id=resolved_map_id,
            stage=stage,
        )
        if course is None or course.id is None:
            return []

        statement = statement.where(
            anchor_pb.scope == scope,
            anchor_pb.course_id == course.id,
            anchor_pb.is_pro_only.is_(_is_pro_only_from_record_type(record_type)),
        )
        if steamid64 is not None:
            statement = statement.where(anchor_pb.steamid64 == steamid64)
        statement = statement.order_by(Record.time.asc(), Record.uuid.asc())
    elif steamid64 is not None:
        course = aliased(MapCourse)
        statement = (
            statement.join(course, course.id == anchor_pb.course_id)
            .where(
                anchor_pb.scope == scope,
                anchor_pb.steamid64 == steamid64,
                anchor_pb.is_pro_only.is_(_is_pro_only_from_record_type(record_type)),
                course.stage == stage,
            )
            .order_by(
                course.map_id.asc(),
                course.stage.asc(),
                Record.time.asc(),
                Record.uuid.asc(),
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
            player={
                "steamid64": str(record_steamid64),
                "display_name": player_name,
            },
            steam_id=None,
            server_id=server_id,
            server_name=server_name or "",
            map_id=record_map_id,
            map_name=map_name,
            map_tier=tiers_by_course[(record_map_id, record_stage)],
            mode_id=record_mode.mode_id,
            mode=mode_name.value,
            stage=record_stage,
            tickrate=128,
            time=float(record_time),
            teleports=record_teleports,
            points=points,
            created_on=created_on,
            updated_on=updated_on,
            updated_by=str(updated_by),
            replay_id=replay_id,
            is_replay_available=has_run_replay(
                map_name=map_name,
                replay_id=record_uuid,
            ),
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
            record_mode,
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


async def read_map_pb_leaderboard(
    *,
    session: AsyncSession,
    map_id: int,
    stage: int,
    scope: ModeScope,
    record_type: RecordType,
    country: str | None = None,
    region: str | None = None,
    exclude_cheaters: bool = True,
    offset: int = 0,
    limit: int = 100,
    viewer_steamid64: int | None = None,
    friends_viewer_steamid64: int | None = None,
) -> MapPbLeaderboardPublic:
    course = await get_map_course_by_map_stage(
        session=session,
        map_id=map_id,
        stage=stage,
    )
    if course is None or course.id is None:
        return MapPbLeaderboardPublic(
            data=[],
            count=0,
            unique_nub_finishes=0,
            unique_pro_finishes=0,
            current_user_rank=None,
            current_user_steamid64=str(viewer_steamid64) if viewer_steamid64 is not None else None,
        )

    geography_country_codes = (
        (country,) if country is not None else get_region_country_codes(region)
    )
    is_pro_only = _is_pro_only_from_record_type(record_type)

    counts_statement = (
        select(
            RecordPb.is_pro_only.label("is_pro_only"),
            func.count().label("count"),
        )
        .select_from(RecordPb)
        .where(
            col(RecordPb.scope) == scope,
            col(RecordPb.course_id) == course.id,
        )
        .group_by(RecordPb.is_pro_only)
    )
    if geography_country_codes is not None:
        counts_statement = counts_statement.join(
            Player,
            col(Player.steamid64) == col(RecordPb.steamid64),
        ).where(col(Player.country).in_(list(geography_country_codes)))
    if friends_viewer_steamid64 is not None:
        counts_statement = counts_statement.where(
            _friend_or_self_clause(
                steamid64_column=col(RecordPb.steamid64),
                viewer_steamid64=friends_viewer_steamid64,
            )
        )
    if exclude_cheaters:
        counts_statement = counts_statement.where(
            _not_active_ban_exists_split_clause(steamid64_column=col(RecordPb.steamid64))
        )

    counts_by_type = {
        bool(result_is_pro_only): int(result_count or 0)
        for result_is_pro_only, result_count in (await session.exec(counts_statement)).all()
    }
    unique_nub_finishes = counts_by_type.get(False, 0)
    unique_pro_finishes = counts_by_type.get(True, 0)
    total_count = counts_by_type.get(is_pro_only, 0)

    anchor_pb = aliased(RecordPb)
    pro_pb = aliased(RecordPb)
    ovr_pb = aliased(RecordPb)
    scoped_points = (
        pro_pb.points if is_pro_only else func.coalesce(ovr_pb.points, 0)
    )
    public_scoped_points = case(
        (active_ban_exists_clause(steamid64_column=col(Record.steamid64)), 0),
        else_=scoped_points,
    )

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
            Record.mode,
            Mode.name_short,
            Record.stage,
            Record.time,
            Record.teleports,
            public_scoped_points.label("points"),
            Record.created_at,
            Record.updated_at,
            Record.updated_by,
            Record.replay_id,
            Record.is_valid,
        )
        .select_from(Record)
        .join(anchor_pb, anchor_pb.record_uuid == Record.uuid)
        .join(Player, col(Record.steamid64) == col(Player.steamid64))
        .join(ServerGlobalapi, col(Record.server_id) == col(ServerGlobalapi.id))
        .join(Map, col(Record.map_id) == col(Map.id))
        .join(Mode, col(Record.mode) == col(Mode.name_short))
        .outerjoin(
            pro_pb,
            and_(
                pro_pb.record_uuid == Record.uuid,
                pro_pb.scope == scope,
                pro_pb.is_pro_only.is_(True),
            ),
        )
        .outerjoin(
            ovr_pb,
            and_(
                ovr_pb.record_uuid == Record.uuid,
                ovr_pb.scope == scope,
                ovr_pb.is_pro_only.is_(False),
            ),
        )
        .where(
            anchor_pb.scope == scope,
            anchor_pb.course_id == course.id,
            anchor_pb.is_pro_only.is_(is_pro_only),
        )
        .order_by(Record.time.asc(), Record.uuid.asc())
        .offset(offset)
        .limit(limit)
    )
    if geography_country_codes is not None:
        statement = statement.where(col(Player.country).in_(list(geography_country_codes)))
    if friends_viewer_steamid64 is not None:
        statement = statement.where(
            _friend_or_self_clause(
                steamid64_column=col(Record.steamid64),
                viewer_steamid64=friends_viewer_steamid64,
            )
        )
    if exclude_cheaters:
        statement = statement.where(
            not_active_ban_exists_clause(steamid64_column=col(Record.steamid64))
        )

    rows = (await session.exec(statement)).all()
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
    data = [
        RecordPublic(
            uuid=record_uuid,
            id=record_id,
            player={
                "steamid64": str(record_steamid64),
                "display_name": player_name,
            },
            steam_id=None,
            server_id=server_id,
            server_name=server_name or "",
            map_id=record_map_id,
            map_name=map_name,
            map_tier=tiers_by_course[(record_map_id, record_stage)],
            mode_id=record_mode.mode_id,
            mode=mode_name.value,
            stage=record_stage,
            tickrate=128,
            time=float(record_time),
            teleports=record_teleports,
            points=points,
            created_on=created_on,
            updated_on=updated_on,
            updated_by=str(updated_by),
            replay_id=replay_id,
            is_replay_available=has_run_replay(
                map_name=map_name,
                replay_id=record_uuid,
            ),
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
            record_mode,
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

    current_user_rank: int | None = None
    if viewer_steamid64 is not None and total_count > 0:
        rank_subquery = (
            select(
                RecordPb.steamid64.label("steamid64"),
                func.row_number()
                .over(order_by=(Record.time.asc(), Record.uuid.asc()))
                .label("rank"),
            )
            .select_from(RecordPb)
            .join(Record, Record.uuid == RecordPb.record_uuid)
            .where(
                col(RecordPb.scope) == scope,
                col(RecordPb.course_id) == course.id,
                col(RecordPb.is_pro_only).is_(is_pro_only),
            )
        )
        if geography_country_codes is not None:
            rank_subquery = rank_subquery.join(
                Player,
                col(Player.steamid64) == col(RecordPb.steamid64),
            ).where(col(Player.country).in_(list(geography_country_codes)))
        if friends_viewer_steamid64 is not None:
            rank_subquery = rank_subquery.where(
                _friend_or_self_clause(
                    steamid64_column=col(RecordPb.steamid64),
                    viewer_steamid64=friends_viewer_steamid64,
                )
            )
        if exclude_cheaters:
            rank_subquery = rank_subquery.where(
                _not_active_ban_exists_split_clause(
                    steamid64_column=col(RecordPb.steamid64)
                )
            )
        ranked_rows = rank_subquery.subquery()
        current_user_rank = (
            await session.exec(
                select(ranked_rows.c.rank).where(
                    ranked_rows.c.steamid64 == viewer_steamid64
                )
            )
        ).first()

    return MapPbLeaderboardPublic(
        data=data,
        count=total_count,
        unique_nub_finishes=unique_nub_finishes,
        unique_pro_finishes=unique_pro_finishes,
        current_user_rank=current_user_rank,
        current_user_steamid64=str(viewer_steamid64) if viewer_steamid64 is not None else None,
    )


async def read_record_ranks(
    *,
    session: AsyncSession,
    record_uuids: Sequence[uuid.UUID],
    scope: ModeScope,
    record_type: RecordType,
    country: str | None = None,
) -> list[tuple[uuid.UUID, int | None, int | None]]:
    if not record_uuids:
        return []

    is_pro_only = _is_pro_only_from_record_type(record_type)
    unique_record_uuids = list(dict.fromkeys(record_uuids))
    target_statement = (
        select(
            RecordPb.record_uuid.label("record_uuid"),
            RecordPb.course_id.label("course_id"),
        )
        .select_from(RecordPb)
        .where(
            col(RecordPb.record_uuid).in_(unique_record_uuids),
            col(RecordPb.scope) == scope,
            col(RecordPb.is_pro_only).is_(is_pro_only),
            _not_active_ban_exists_split_clause(
                steamid64_column=col(RecordPb.steamid64)
            ),
        )
    )
    if country is not None:
        target_statement = target_statement.join(
            Player,
            col(Player.steamid64) == col(RecordPb.steamid64),
        ).where(col(Player.country) == country)

    target_rows = (await session.exec(target_statement)).all()
    target_course_ids = sorted({course_id for _record_uuid, course_id in target_rows})
    if not target_course_ids:
        return [(record_uuid, None, None) for record_uuid in record_uuids]

    ranked_statement = (
        select(
            RecordPb.record_uuid.label("record_uuid"),
            RecordPb.course_id.label("course_id"),
            func.row_number()
            .over(
                partition_by=RecordPb.course_id,
                order_by=(
                    Record.time.asc(),
                    Record.uuid.asc(),
                ),
            )
            .label("rank"),
            func.count()
            .over(partition_by=RecordPb.course_id)
            .label("total_count"),
        )
        .select_from(RecordPb)
        .join(Record, Record.uuid == RecordPb.record_uuid)
        .where(
            col(RecordPb.scope) == scope,
            col(RecordPb.is_pro_only).is_(is_pro_only),
            col(RecordPb.course_id).in_(target_course_ids),
            _not_active_ban_exists_split_clause(
                steamid64_column=col(RecordPb.steamid64)
            ),
        )
    )
    if country is not None:
        ranked_statement = ranked_statement.join(
            Player,
            col(Player.steamid64) == col(RecordPb.steamid64),
        ).where(col(Player.country) == country)

    ranked_rows = (await session.exec(ranked_statement)).all()
    rank_by_uuid = {
        record_uuid: (rank, total_count)
        for record_uuid, _course_id, rank, total_count in ranked_rows
    }

    return [
        (
            record_uuid,
            rank_by_uuid.get(record_uuid, (None, None))[0],
            rank_by_uuid.get(record_uuid, (None, None))[1],
        )
        for record_uuid in record_uuids
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
        col(Record.mode) == record.mode,
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
    exclude_cheaters: bool,
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
                statement = statement.where(
                    col(Record.mode).in_([legacy_mode_id_to_kz_mode(mode_id) for mode_id in mode_ids])
                )
            if exclude_cheaters:
                statement = statement.where(
                    not_active_ban_exists_clause(
                        steamid64_column=col(Record.steamid64)
                    )
                )
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
            exclude_cheaters=exclude_cheaters,
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
    exclude_cheaters: bool,
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
        statement = statement.where(
            col(Record.mode).in_([legacy_mode_id_to_kz_mode(mode_id) for mode_id in mode_ids])
        )
    if exclude_cheaters:
        statement = statement.where(
            not_active_ban_exists_clause(steamid64_column=col(Record.steamid64))
        )
    if has_teleports is True:
        statement = statement.where(col(Record.teleports) > 0)
        distinct_columns = [col(Record.map_id), col(Record.stage), col(Record.mode)]
        order_columns = [
            col(Record.map_id),
            col(Record.stage),
            col(Record.mode),
            col(Record.time).asc(),
            *_record_tie_breakers(),
        ]
    elif has_teleports is False:
        statement = statement.where(col(Record.teleports) == 0)
        distinct_columns = [col(Record.map_id), col(Record.stage), col(Record.mode)]
        order_columns = [
            col(Record.map_id),
            col(Record.stage),
            col(Record.mode),
            col(Record.time).asc(),
            *_record_tie_breakers(),
        ]
    else:
        bucket = _teleports_bucket_expression()
        distinct_columns = [
            col(Record.map_id),
            col(Record.stage),
            col(Record.mode),
            bucket,
        ]
        order_columns = [
            col(Record.map_id),
            col(Record.stage),
            col(Record.mode),
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
        statement = statement.where(
            col(Record.mode).in_([legacy_mode_id_to_kz_mode(mode_id) for mode_id in mode_ids])
        )
    if stage is not None:
        statement = statement.where(col(Record.stage) == stage)
    if has_teleports is True:
        statement = statement.where(col(Record.teleports) > 0)
    elif has_teleports is False:
        statement = statement.where(col(Record.teleports) == 0)
    if created_since is not None:
        statement = statement.where(col(Record.created_at) >= created_since)

    statement = statement.order_by(
        col(Record.created_at).desc(),
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
            col(Record.mode) == record.mode,
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
