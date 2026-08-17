import math
import uuid
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from sqlalchemy import (
    and_,
    bindparam,
    case,
    delete,
    exists,
    func,
    or_,
    text,
    true,
    update,
)
from sqlalchemy.orm import aliased
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.regions import get_region_country_codes
from app.models import (
    Ban,
    KZMode,
    Map,
    MapCourse,
    MapCourseTier,
    MapPbLeaderboardPublic,
    MapWrHistoryEntryPublic,
    MapWrHistoryPublic,
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
    RecordPbSortBy,
    RecordPublic,
    RecordRunHistoryEntryPublic,
    RecordRunHistoryPublic,
    RecordType,
    ServerGlobalapi,
    ServerGlobalapiCompatPublicV0,
    ServerGroup,
    ServerGroupSummary,
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
    calculate_course_pb_points,
    calculate_estimated_pb_points,
)
from app.services.run_replay_storage import has_run_replay

from .ban import active_ban_exists_clause, not_active_ban_exists_clause
from .map import get_map_by_name
from .map_leaderboard import rebuild_map_leaderboards_for_keys
from .player import read_players_batch, steamid64_to_steam2, to_player_ref_public
from .player_notification import create_wr_beaten_notification
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
        _record_pb_table.c["type"] == bindparam("pk_type"),
    )
    .values(
        points=bindparam("next_points"),
        updated_at=bindparam("next_updated_on"),
    )
)


@dataclass(frozen=True, slots=True)
class _WinnerPbEntry:
    record_uuid: uuid.UUID
    time: Decimal
    time_ms: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class _WrSnapshot:
    steamid64: int
    record_uuid: uuid.UUID
    map_id: int
    map_name: str
    scope: ModeScope
    record_type: RecordType
    time: Decimal


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
                col(Ban.expires_at).is_(None),
            )
        ),
        ~exists(
            select(Ban.id).where(
                col(Ban.steamid64) == steamid64_column,
                col(Ban.expires_at) >= func.now(),
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
        "pk_type": record_type,
        "next_points": points,
        "next_updated_on": updated_at,
    }


async def _execute_point_updates(
    *,
    session: AsyncSession,
    updates: Sequence[tuple[dict[str, object], int, int]],
) -> None:
    """Apply WR demotions before promotions protected by the partial index."""
    demotions = [
        params for params, current, next_points in updates
        if current == 1000 and next_points != 1000
    ]
    remaining = [
        params for params, current, next_points in updates
        if not (current == 1000 and next_points != 1000)
    ]
    if demotions:
        await session.execute(_RECORD_PB_POINTS_BULK_UPDATE, demotions)
    if remaining:
        await session.execute(_RECORD_PB_POINTS_BULK_UPDATE, remaining)


def _stored_points_for_banned_record() -> int:
    return 1


def _record_time_to_wr_gap(
    *,
    wr_time: Decimal,
    record_time: Decimal,
) -> float | None:
    wr_time_float = float(wr_time)
    record_time_float = float(record_time)
    if (
        not math.isfinite(wr_time_float)
        or wr_time_float <= 0
        or not math.isfinite(record_time_float)
        or record_time_float <= wr_time_float
    ):
        return None

    ratio_delta = record_time_float / wr_time_float - 1
    if not math.isfinite(ratio_delta) or ratio_delta <= 0:
        return None

    wr_gap = math.log2(ratio_delta)
    return round(wr_gap, 3) if math.isfinite(wr_gap) else None


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
        or_(col(Ban.expires_at).is_(None), col(Ban.expires_at) >= func.now()),
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
        or_(col(Ban.expires_at).is_(None), col(Ban.expires_at) >= func.now()),
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
        RecordPb.type,
        case(
            (active_ban_exists_clause(steamid64_column=col(RecordPb.steamid64)), 0),
            else_=RecordPb.points,
        ).label("points"),
    ).where(
        col(RecordPb.record_uuid).in_(list(record_uuids)),
        col(RecordPb.scope) == scope,
    )
    points_by_uuid: dict[uuid.UUID, dict[RecordType, int]] = {}
    for record_uuid, row_record_type, points in (await session.exec(statement)).all():
        current = points_by_uuid.setdefault(record_uuid, {})
        current[row_record_type] = points

    return {
        record_uuid: _resolve_scoped_points(
            pro_points=values.get(RecordType.PRO),
            ovr_points=values.get(RecordType.NUB),
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
                time=time_seconds,
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
        select(RecordPb.record_uuid, RecordPb.time)
        .where(
            col(RecordPb.scope) == mode_scope_from_id(scope_id),
            col(RecordPb.course_id) == course_id,
            col(RecordPb.type) == record_type,
            _not_active_ban_exists_split_clause(
                steamid64_column=col(RecordPb.steamid64)
            ),
        )
        .order_by(col(RecordPb.time).asc(), col(RecordPb.record_uuid).asc())
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


async def recalculate_estimated_record_pb_points_for_player(
    *,
    session: AsyncSession,
    steamid64: int,
) -> int:
    """Refresh one player's PB points without recomputing the whole bucket.

    This intentionally uses the incremental estimate applied when a PB is first
    created. It is useful after an unban, when the player's preserved PB rows
    still carry the banned fallback point value.
    """
    rows = (
        await session.exec(
            select(RecordPb)
            .where(col(RecordPb.steamid64) == steamid64)
            .order_by(
                col(RecordPb.scope).asc(),
                col(RecordPb.course_id).asc(),
                col(RecordPb.type).asc(),
            )
        )
    ).all()
    if not rows:
        return 0

    wr_bucket_keys: set[tuple[ModeScope, int, RecordType]] = set()
    rebuilt_wr_rows = 0

    if await _steamid64_has_active_ban(session=session, steamid64=steamid64):
        estimated_points_by_row_key = {
            (row.scope, row.course_id, row.type): _stored_points_for_banned_record()
            for row in rows
        }
    else:
        scopes = {row.scope for row in rows}
        course_ids = sorted({row.course_id for row in rows})
        tier_rows = (
            await session.exec(
                select(
                    MapCourseTier.course_id,
                    MapCourseTier.mode,
                    MapCourseTier.tier,
                ).where(col(MapCourseTier.course_id).in_(course_ids))
            )
        ).all()
        tier_values_by_key: dict[tuple[int, ModeScope], list[int]] = defaultdict(list)
        for course_id, mode, tier in tier_rows:
            for scope in scopes:
                if mode in mode_scope_modes(scope) and tier > 0:
                    tier_values_by_key[(course_id, scope)].append(tier)
        tiers_by_course_and_scope = {
            (course_id, scope): min(tier_values_by_key[(course_id, scope)], default=0)
            for course_id in course_ids
            for scope in scopes
        }

        # Keep the player's buckets in a small materialized relation, then join
        # every unbanned PB row to it once. This is deliberately set-based: a
        # prolific player can have thousands of PB buckets, for which one table
        # scan is much cheaper than thousands of separate bucket scans.
        target_record_pbs = (
            select(
                col(RecordPb.record_uuid).label("record_uuid"),
                col(RecordPb.course_id).label("course_id"),
                col(RecordPb.scope).label("scope"),
                col(RecordPb.type).label("record_type"),
                col(RecordPb.time).label("time"),
            )
            .where(col(RecordPb.steamid64) == steamid64)
            .cte("target_record_pbs")
            .prefix_with("MATERIALIZED", dialect="postgresql")
        )
        earlier_entry = case(
            (
                or_(
                    col(RecordPb.time) < target_record_pbs.c.time,
                    and_(
                        col(RecordPb.time) == target_record_pbs.c.time,
                        col(RecordPb.record_uuid) < target_record_pbs.c.record_uuid,
                    ),
                ),
                1,
            ),
            else_=0,
        )
        bucket_stats = (
            select(
                target_record_pbs.c.record_uuid,
                target_record_pbs.c.scope,
                target_record_pbs.c.course_id,
                target_record_pbs.c.record_type,
                func.count(RecordPb.record_uuid).label("total"),
                (func.coalesce(func.sum(earlier_entry), 0) + 1).label("rank"),
                func.min(RecordPb.time).label("wr_time"),
            )
            .select_from(
                target_record_pbs.join(
                    RecordPb,
                    and_(
                        col(RecordPb.course_id) == target_record_pbs.c.course_id,
                        col(RecordPb.scope) == target_record_pbs.c.scope,
                        col(RecordPb.type) == target_record_pbs.c.record_type,
                        _not_active_ban_exists_split_clause(
                            steamid64_column=col(RecordPb.steamid64)
                        ),
                    ),
                )
            )
            .group_by(
                target_record_pbs.c.record_uuid,
                target_record_pbs.c.scope,
                target_record_pbs.c.course_id,
                target_record_pbs.c.record_type,
                target_record_pbs.c.time,
            )
        )
        # The planner underestimates the number of rows in popular buckets and
        # otherwise picks thousands of random index scans. Restrict this one
        # transaction to hash/merge joins so `record_pb` is scanned once.
        await session.execute(text("SET LOCAL enable_nestloop = off"))
        bucket_stats = (await session.exec(bucket_stats)).all()
        bucket_stats_by_row_key = {
            (scope, course_id, record_type, record_uuid): (rank, total, wr_time)
            for record_uuid, scope, course_id, record_type, total, rank, wr_time in bucket_stats
        }

        estimated_points_by_row_key = {}
        for row in rows:
            bucket_stats = bucket_stats_by_row_key.get(
                (row.scope, row.course_id, row.type, row.record_uuid)
            )
            if bucket_stats is None:
                raise RuntimeError(
                    f"Missing estimated-points bucket stats for PB {row.record_uuid}"
                )
            rank, total, wr_time = bucket_stats
            estimated_points_by_row_key[(row.scope, row.course_id, row.type)] = (
                calculate_course_pb_points(
                    rank=int(rank),
                    total=int(total),
                    time_ms=seconds_to_time_ms(row.time),
                    wr_time_ms=seconds_to_time_ms(Decimal(wr_time)),
                    tier=tiers_by_course_and_scope[(row.course_id, row.scope)],
                    is_pro_only=row.type.is_pro,
                )
            )

        # A recovered PB can be the new active WR while the old WR row still
        # owns the partial unique 1000-point index. Rebuild only those buckets
        # so the stale WR is demoted before the recovered row is promoted.
        wr_bucket_keys = {
            (row.scope, row.course_id, row.type)
            for row in rows
            if (
                estimated_points_by_row_key[(row.scope, row.course_id, row.type)]
                == 1000
                and row.points != 1000
            )
        }
        for scope, course_id, record_type in wr_bucket_keys:
            rebuilt_wr_rows += await rebuild_record_pb_points_bucket(
                session=session,
                course_id=course_id,
                scope_id=mode_scope_to_id(scope),
                record_type=record_type,
            )

    updated_at = get_datetime_utc()
    raw_updates: list[tuple[dict[str, object], int, int]] = []
    for row in rows:
        if (row.scope, row.course_id, row.type) in wr_bucket_keys:
            continue
        estimated_points = estimated_points_by_row_key[(row.scope, row.course_id, row.type)]
        if row.points == estimated_points:
            continue
        raw_updates.append(
            (
                _record_pb_points_update_params(
                    scope=row.scope,
                    course_id=row.course_id,
                    steamid64=row.steamid64,
                    record_type=row.type,
                    points=estimated_points,
                    updated_at=updated_at,
                ),
                row.points,
                estimated_points,
            )
        )

    if raw_updates:
        await _execute_point_updates(session=session, updates=raw_updates)
        _expunge_loaded_record_pbs(session=session)
    return rebuilt_wr_rows + len(raw_updates)


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
                col(RecordPb.type) == record_type,
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
            existing.time = winner.time
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
                type=record_type,
                record_uuid=winner.record_uuid,
                time=winner.time,
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
            record_type,
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
        existing.time = winner.time
        existing.points = estimated_points
        existing.updated_at = get_datetime_utc()
        session.add(existing)
        return

    session.add(
        RecordPb(
            scope=mode_scope_from_id(scope_id),
            course_id=course_id,
            steamid64=steamid64,
            type=record_type,
            record_uuid=winner.uuid,
            time=winner.time,
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
                RecordPb.type,
                RecordPb.record_uuid,
                RecordPb.time,
                RecordPb.points,
                RecordPb.updated_at,
            )
            .where(
                col(RecordPb.scope) == mode_scope_from_id(scope_id),
                col(RecordPb.course_id) == course_id,
                col(RecordPb.type) == record_type,
            )
            .order_by(col(RecordPb.time).asc(), col(RecordPb.record_uuid).asc())
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
    updates = [
            (
                _record_pb_points_update_params(
                    scope=row_scope_id,
                    course_id=row_course_id,
                    steamid64=steamid64,
                    record_type=row_record_type,
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
    if updates:
        await _execute_point_updates(session=session, updates=updates)
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
            RecordPb.type,
            RecordPb.record_uuid,
            RecordPb.time,
            RecordPb.points,
            RecordPb.updated_at,
        )
        .where(col(RecordPb.course_id) == course_id)
        .order_by(
            col(RecordPb.scope).asc(),
            col(RecordPb.type).asc(),
            col(RecordPb.time).asc(),
            col(RecordPb.record_uuid).asc(),
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
        tuple[ModeScope, RecordType],
        list[tuple[ModeScope, int, int, RecordType, uuid.UUID, Decimal, int, datetime]],
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
    for (scope, row_record_type), bucket_rows in grouped_rows.items():
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
            is_pro_only=row_record_type.is_pro,
        )
        raw_updates.extend(
            (
                _record_pb_points_update_params(
                    scope=row_scope_id,
                    course_id=row_course_id,
                    steamid64=steamid64,
                    record_type=row_record_type,
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

    if raw_updates:
        await _execute_point_updates(session=session, updates=raw_updates)
        _expunge_loaded_record_pbs(session=session)
    return len(raw_updates)


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
            RecordPb.type,
            RecordPb.record_uuid,
            RecordPb.updated_at,
            Record.mode,
            Record.steamid64,
            RecordPb.time,
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
        .order_by(RecordPb.type.asc(), MapCourse.map_id.asc())
    )
    if map_id is not None:
        statement = statement.where(MapCourse.map_id == map_id)
    if record_type is not None:
        statement = statement.where(RecordPb.type == record_type)

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
            type=row_record_type,
            mode_id=mode.mode_id,
            player=to_player_ref_public(player=players_by_steamid64[player_steamid64]),
            time=float(record_time),
            updated_at=updated_at,
        )
        for (
            row_map_id,
            row_scope,
            row_record_type,
            record_uuid,
            updated_at,
            mode,
            player_steamid64,
            record_time,
        ) in rows
    ]


async def read_map_wr_history(
    *,
    session: AsyncSession,
    map_id: int,
    scope: ModeScope,
    record_type: RecordType,
) -> MapWrHistoryPublic:
    order_by = (
        col(Record.created_at).asc(),
        col(Record.id).asc().nullslast(),
        col(Record.uuid).asc(),
    )
    ordered = (
        select(
            col(Record.uuid).label("record_uuid"),
            col(Record.steamid64),
            col(Record.server_id),
            col(Record.mode),
            col(Record.teleports),
            col(Record.time),
            col(Record.created_at),
            col(Record.id),
            func.min(col(Record.time))
            .over(order_by=order_by, rows=(None, -1))
            .label("previous_wr"),
        )
        .where(
            col(Record.map_id) == map_id,
            col(Record.stage) == 0,
            col(Record.is_valid).is_(True),
            col(Record.mode).in_(list(mode_scope_modes(scope))),
            not_active_ban_exists_clause(steamid64_column=col(Record.steamid64)),
        )
        .order_by(*order_by)
    )
    if record_type.is_pro:
        ordered = ordered.where(col(Record.teleports) == 0)

    ordered_cte = ordered.cte("ordered")
    events_cte = (
        select(ordered_cte)
        .where(
            or_(
                ordered_cte.c.previous_wr.is_(None),
                ordered_cte.c.time < ordered_cte.c.previous_wr,
            )
        )
        .cte("events")
    )
    rows = (
        await session.exec(
            select(
                events_cte.c.record_uuid,
                Player,
                events_cte.c.server_id,
                ServerGlobalapi.name,
                Mode,
                events_cte.c.teleports,
                events_cte.c.time,
                events_cte.c.created_at,
            )
            .join(Player, col(Player.steamid64) == events_cte.c.steamid64)
            .join(ServerGlobalapi, col(ServerGlobalapi.id) == events_cte.c.server_id)
            .join(Mode, col(Mode.name_short) == events_cte.c.mode)
            .order_by(
                events_cte.c.created_at.asc(),
                events_cte.c.id.asc().nullslast(),
                events_cte.c.record_uuid.asc(),
            )
        )
    ).all()

    if rows:
        first_wr_created_at = rows[0][7]
        stabilization_end = first_wr_created_at + timedelta(days=30)
        initial_window_rows = [
            row for row in rows if row[7] < stabilization_end
        ]
        first_wr = min(
            initial_window_rows,
            key=lambda row: (row[6], row[7], str(row[0])),
        )
        rows = [
            first_wr,
            *(row for row in rows if row[7] >= stabilization_end),
        ]

    entries = [
        MapWrHistoryEntryPublic(
            record_uuid=record_uuid,
            player=to_player_ref_public(player=player),
            server_id=server_id,
            server_name=server_name or "",
            mode_id=mode.name_short.mode_id,
            mode=mode.name_short,
            teleports=teleports,
            time=float(record_time),
            created_on=created_on,
        )
        for (
            record_uuid,
            player,
            server_id,
            server_name,
            mode,
            teleports,
            record_time,
            created_on,
        ) in rows
    ]
    return MapWrHistoryPublic(data=entries, count=len(entries))


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


async def _load_wr_snapshots_for_bucket_keys(
    *,
    session: AsyncSession,
    bucket_keys: set[tuple[int, int, RecordType]],
) -> dict[tuple[int, int, RecordType], _WrSnapshot]:
    if not bucket_keys:
        return {}

    snapshots: dict[tuple[int, int, RecordType], _WrSnapshot] = {}
    for scope_id, course_id, record_type in sorted(bucket_keys):
        scope = mode_scope_from_id(scope_id)
        row = (
            await session.exec(
                select(
                    RecordPb.steamid64,
                    RecordPb.record_uuid,
                    MapCourse.map_id,
                    Map.name,
                    RecordPb.time,
                )
                .join(MapCourse, col(MapCourse.id) == col(RecordPb.course_id))
                .join(Map, col(Map.id) == col(MapCourse.map_id))
                .where(
                    col(RecordPb.scope) == scope,
                    col(RecordPb.course_id) == course_id,
                    col(RecordPb.type) == record_type,
                    col(RecordPb.points) == 1000,
                )
            )
        ).first()
        if row is None:
            continue

        steamid64, record_uuid, map_id, map_name, record_time = row
        snapshots[(scope_id, course_id, record_type)] = _WrSnapshot(
            steamid64=steamid64,
            record_uuid=record_uuid,
            map_id=map_id,
            map_name=map_name,
            scope=scope,
            record_type=record_type,
            time=record_time,
        )
    return snapshots


async def _create_wr_beaten_notifications_for_changes(
    *,
    session: AsyncSession,
    before: dict[tuple[int, int, RecordType], _WrSnapshot],
    after: dict[tuple[int, int, RecordType], _WrSnapshot],
) -> None:
    for key, previous_wr in before.items():
        current_wr = after.get(key)
        if current_wr is None:
            continue
        if current_wr.record_uuid == previous_wr.record_uuid:
            continue
        await create_wr_beaten_notification(
            session=session,
            previous_owner_steamid64=previous_wr.steamid64,
            new_owner_steamid64=current_wr.steamid64,
            map_id=current_wr.map_id,
            map_name=current_wr.map_name,
            scope=current_wr.scope,
            record_type=current_wr.record_type,
            previous_record_uuid=previous_wr.record_uuid,
            new_record_uuid=current_wr.record_uuid,
            new_record_time=current_wr.time,
            commit=False,
        )


async def _refresh_record_read_models_for_change(
    *,
    session: AsyncSession,
    before: Record | None,
    after: Record | None,
    emit_wr_notifications: bool = False,
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

    bucket_keys = {
        (scope_id, course_id, record_type)
        for scope_id, course_id, _steamid64, record_type in pb_keys
    }
    wr_snapshots_before = (
        await _load_wr_snapshots_for_bucket_keys(
            session=session,
            bucket_keys=bucket_keys,
        )
        if emit_wr_notifications
        else {}
    )

    await rebuild_record_pb_buckets_for_keys(
        session=session,
        keys=pb_keys,
        time_changed_record_uuids=time_changed_record_uuids,
    )
    if emit_wr_notifications:
        wr_snapshots_after = await _load_wr_snapshots_for_bucket_keys(
            session=session,
            bucket_keys=bucket_keys,
        )
        await _create_wr_beaten_notifications_for_changes(
            session=session,
            before=wr_snapshots_before,
            after=wr_snapshots_after,
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
        owner_steamid64=(
            str(server.owner_steamid64) if server.owner_steamid64 is not None else "0"
        ),
    )


def _to_server_group_summary(
    *,
    group: ServerGroup | None,
) -> ServerGroupSummary | None:
    if group is None:
        return None
    return ServerGroupSummary(
        id=group.id,
        name=group.name,
        custom_id=group.custom_id,
    )


def _to_server_group_summary_from_values(
    *,
    group_id: uuid.UUID | None,
    group_name: str | None,
    group_custom_id: str | None,
) -> ServerGroupSummary | None:
    if group_id is None or group_name is None or group_custom_id is None:
        return None
    return ServerGroupSummary(
        id=group_id,
        name=group_name,
        custom_id=group_custom_id,
    )


def to_record_public(
    *,
    record: Record,
    player: Player,
    server: ServerGlobalapi,
    server_group: ServerGroup | None = None,
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
        server_group=_to_server_group_summary(group=server_group),
        map_id=record.map_id,
        map_name=map_obj.name,
        workshop_id=map_obj.workshop_id,
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
    server_group: ServerGroup | None = None,
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
            group=_to_server_group_summary(group=server_group),
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
        steamid64=str(record.steamid64),
        player_name=player.name,
        steam_id=steamid64_to_steam2(record.steamid64),
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
        select(Record, Player, ServerGlobalapi, ServerGroup, Map, Mode)
        .join(Player, col(Record.steamid64) == col(Player.steamid64))
        .join(ServerGlobalapi, col(Record.server_id) == col(ServerGlobalapi.id))
        .outerjoin(ServerGroup, col(ServerGlobalapi.group_id) == col(ServerGroup.id))
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
            server_group=server_group,
            map_obj=map_obj,
            mode=mode,
            map_tier=tiers_by_course[(record.map_id, record.stage)],
            points=points_by_uuid.get(record.uuid, 0),
        )
        for record, player, server, server_group, map_obj, mode in rows
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

    scoped_tier = (
        select(func.coalesce(func.min(func.nullif(MapCourseTier.tier, 0)), 0))
        .select_from(MapCourse)
        .join(MapCourseTier, col(MapCourseTier.course_id) == col(MapCourse.id))
        .where(
            col(MapCourse.map_id) == col(Record.map_id),
            col(MapCourse.stage) == col(Record.stage),
            col(MapCourseTier.mode).in_(list(mode_scope_modes(query.scope))),
        )
        .correlate(Record)
        .scalar_subquery()
    )

    def apply_recent_record_filters(statement: Any) -> Any:
        if requested_record_type is RecordType.PRO or query.is_pro_only is True:
            statement = statement.where(col(Record.teleports) == 0)
        elif requested_record_type is RecordType.NUB:
            statement = statement.where(col(Record.teleports) > 0)
        statement = statement.where(
            col(Record.mode).in_(list(mode_scope_modes(query.scope)))
        )
        if query.mode is not None:
            statement = statement.where(col(Record.mode) == query.mode)
        if query.map_id is not None:
            statement = statement.where(col(Record.map_id) == query.map_id)
        if query.stage is not None:
            statement = statement.where(col(Record.stage) == query.stage)
        if query.is_bonus is True:
            statement = statement.where(col(Record.stage) > 0)
        elif query.is_bonus is False:
            statement = statement.where(col(Record.stage) == 0)
        if query.tier is not None:
            statement = statement.where(scoped_tier == query.tier)
        if query.points_more_or_equal_than is not None:
            statement = statement.where(
                public_scoped_points >= query.points_more_or_equal_than
            )
        if query.points_less_or_equal_than is not None:
            statement = statement.where(
                public_scoped_points <= query.points_less_or_equal_than
            )
        return statement

    statement = (
        select(
            Record,
            Player,
            ServerGlobalapi,
            ServerGroup,
            Map,
            Mode,
            public_scoped_points.label("points"),
        )
        .join(Player, col(Record.steamid64) == col(Player.steamid64))
        .join(ServerGlobalapi, col(Record.server_id) == col(ServerGlobalapi.id))
        .outerjoin(ServerGroup, col(ServerGlobalapi.group_id) == col(ServerGroup.id))
        .join(Map, col(Record.map_id) == col(Map.id))
        .join(Mode, col(Record.mode) == col(Mode.name_short))
        .outerjoin(
            pro_pb,
            and_(
                pro_pb.record_uuid == Record.uuid,
                pro_pb.scope == query.scope,
                pro_pb.type == RecordType.PRO,
            ),
        )
        .outerjoin(
            ovr_pb,
            and_(
                ovr_pb.record_uuid == Record.uuid,
                ovr_pb.scope == query.scope,
                ovr_pb.type == RecordType.NUB,
            ),
        )
        .where(col(Record.is_valid).is_(True))
    )
    statement = apply_recent_record_filters(statement)

    is_unfiltered_recent_query = (
        query.scope is ModeScope.OVR
        and query.mode is None
        and query.map_id is None
        and query.stage is None
        and query.is_bonus is None
        and query.tier is None
        and query.points_more_or_equal_than is None
        and query.points_less_or_equal_than is None
        and query.is_pro_only is not True
        and requested_record_type is None
    )

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
    if is_unfiltered_recent_query:
        count = await _estimate_record_count(session=session, is_valid=True)
    else:
        count = query.offset + len(rows)
    tiers_by_course = await _load_scoped_record_tiers(
        session=session,
        record_courses=[
            (record.map_id, record.stage)
            for record, _player, _server, _server_group, _map_obj, _mode, _points in rows
        ],
        scope=query.scope,
    )
    return (
        [
            to_recent_record_public(
                record=record,
                player=player,
                server=server,
                server_group=server_group,
                map_obj=map_obj,
                mode=mode,
                map_tier=tiers_by_course[(record.map_id, record.stage)],
                points=points,
            )
            for record, player, server, server_group, map_obj, mode, points in rows
        ],
        count,
    )


async def read_record_run_history(
    *,
    session: AsyncSession,
    steamid64: int,
    map_id: int,
    stage: int,
    scope: ModeScope,
    record_type: RecordType,
    exclude_cheaters: bool = True,
) -> RecordRunHistoryPublic:
    course = await get_map_course_by_map_stage(
        session=session,
        map_id=map_id,
        stage=stage,
    )
    if course is None or course.id is None:
        return RecordRunHistoryPublic(data=[], count=0, wr_time=None)

    wr_time_statement = select(func.min(RecordPb.time)).where(
        col(RecordPb.scope) == scope,
        col(RecordPb.course_id) == course.id,
        col(RecordPb.type) == record_type,
        not_active_ban_exists_clause(steamid64_column=col(RecordPb.steamid64)),
    )
    wr_time = (await session.exec(wr_time_statement)).one()

    statement = (
        select(Record, ServerGlobalapi.name, Map.name)
        .join(ServerGlobalapi, col(Record.server_id) == col(ServerGlobalapi.id))
        .join(Map, col(Record.map_id) == col(Map.id))
        .where(
            col(Record.is_valid).is_(True),
            col(Record.steamid64) == steamid64,
            col(Record.map_id) == map_id,
            col(Record.stage) == stage,
            col(Record.mode).in_(list(mode_scope_modes(scope))),
        )
        .order_by(col(Record.created_at).asc(), *_record_tie_breakers())
    )
    if record_type.is_pro:
        statement = statement.where(col(Record.teleports) == 0)
    if exclude_cheaters:
        statement = statement.where(
            not_active_ban_exists_clause(steamid64_column=col(Record.steamid64))
        )

    rows = (await session.exec(statement)).all()
    best_time_ms: int | None = None
    entries: list[RecordRunHistoryEntryPublic] = []
    for record, server_name, map_name in rows:
        record_time_ms = seconds_to_time_ms(record.time)
        is_pb = best_time_ms is None or record_time_ms < best_time_ms
        if is_pb:
            best_time_ms = record_time_ms

        entries.append(
            RecordRunHistoryEntryPublic(
                uuid=record.uuid,
                id=record.id,
                server_id=record.server_id,
                server_name=server_name or "",
                mode_id=record.mode.mode_id,
                mode=record.mode.value,
                time=float(record.time),
                teleports=record.teleports,
                wr_gap=(
                    _record_time_to_wr_gap(wr_time=wr_time, record_time=record.time)
                    if wr_time is not None
                    else None
                ),
                is_pb=is_pb,
                created_on=record.created_at,
                is_replay_available=has_run_replay(
                    map_name=map_name,
                    replay_id=record.uuid,
                ),
            )
        )

    return RecordRunHistoryPublic(
        data=entries,
        count=len(entries),
        wr_time=float(wr_time) if wr_time is not None else None,
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
        select(Record, Player, ServerGlobalapi, ServerGroup, Map, Mode)
        .join(Player, col(Record.steamid64) == col(Player.steamid64))
        .join(ServerGlobalapi, col(Record.server_id) == col(ServerGlobalapi.id))
        .outerjoin(ServerGroup, col(ServerGlobalapi.group_id) == col(ServerGroup.id))
        .join(Map, col(Record.map_id) == col(Map.id))
        .join(Mode, col(Record.mode) == col(Mode.name_short))
        .where(col(Record.uuid) == record_uuid)
        .where(col(Record.mode).in_(list(mode_scope_modes(scope))))
        .limit(1)
    )
    row = (await session.exec(statement)).first()
    if row is None:
        return None

    record, player, server, server_group, map_obj, mode = row
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
        server_group=server_group,
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
    emit_wr_notifications: bool = False,
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
            emit_wr_notifications=emit_wr_notifications,
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
        emit_wr_notifications=emit_wr_notifications,
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
    steamid64s: Sequence[int] | None,
    mode_ids: Sequence[int],
    teleports_type: TeleportsType,
    server_ids: Sequence[int] | None,
    exclude_cheaters: bool,
    use_gokz_top_points: bool,
    offset: int,
    limit: int,
) -> list[tuple[Record, int]]:
    if map_id is None and steamid64 is None and not steamid64s:
        return []

    scope = ModeScope.OVR
    if mode_ids:
        mode_set = {legacy_mode_id_to_kz_mode(mode_id) for mode_id in mode_ids}
        if mode_set <= {KZMode.KZT, KZMode.NKZ}:
            scope = ModeScope.KZT
        elif mode_set == {KZMode.SKZ}:
            scope = ModeScope.SKZ
        elif mode_set == {KZMode.VNL}:
            scope = ModeScope.VNL

    record_types = [RecordType.NUB]
    if teleports_type == TeleportsType.PRO:
        record_types = [RecordType.PRO]
    elif teleports_type == TeleportsType.OVR:
        record_types = [RecordType.NUB, RecordType.PRO]

    statement = (
        select(
            Record,
            (RecordPb.points if use_gokz_top_points else Record.points).label("points"),
        )
        .select_from(RecordPb)
        .join(Record, col(Record.uuid) == col(RecordPb.record_uuid))
        .join(MapCourse, col(MapCourse.id) == col(RecordPb.course_id))
        .join(Map, col(Map.id) == col(MapCourse.map_id))
        .where(
            col(RecordPb.scope) == scope,
            col(RecordPb.type).in_(record_types),
            col(Record.is_valid).is_(True),
        )
    )
    if teleports_type == TeleportsType.NUB:
        statement = statement.where(~col(Map.name).startswith("kzpro_"))
    if map_id is not None:
        statement = statement.where(
            col(MapCourse.map_id) == map_id,
            col(MapCourse.stage) == stage,
        )
    if steamid64 is not None:
        statement = statement.where(col(RecordPb.steamid64) == steamid64)
        if map_id is None:
            statement = statement.where(col(MapCourse.stage) == stage)
    elif steamid64s:
        statement = statement.where(col(RecordPb.steamid64).in_(list(steamid64s)))
        if map_id is None:
            statement = statement.where(col(MapCourse.stage) == stage)
    if mode_ids:
        statement = statement.where(
            col(Record.mode).in_([legacy_mode_id_to_kz_mode(mode_id) for mode_id in mode_ids])
        )
    if server_ids:
        statement = statement.where(col(Record.server_id).in_(list(server_ids)))
    if exclude_cheaters:
        statement = statement.where(
            not_active_ban_exists_clause(steamid64_column=col(RecordPb.steamid64))
        )
    if teleports_type == TeleportsType.PRO:
        statement = statement.where(col(Record.teleports) == 0)

    if map_id is not None:
        statement = statement.order_by(
            col(RecordPb.time).asc(),
            col(RecordPb.record_uuid).asc(),
        )
    else:
        statement = statement.order_by(
            col(MapCourse.map_id).asc(),
            col(MapCourse.stage).asc(),
            col(Record.mode).asc(),
            col(RecordPb.type).asc(),
            col(RecordPb.time).asc(),
            col(RecordPb.record_uuid).asc(),
        )
    statement = statement.offset(offset).limit(limit)
    return [(record, points) for record, points in (await session.exec(statement)).all()]


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
            .select_from(RecordPb)
            .join(Record, Record.uuid == RecordPb.record_uuid)
            .where(
                RecordPb.scope == scope,
                RecordPb.course_id == course.id,
                RecordPb.type == record_type,
            )
            .order_by(RecordPb.time.asc(), RecordPb.record_uuid.asc())
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
            .select_from(RecordPb)
            .join(Record, Record.uuid == RecordPb.record_uuid)
            .join(course, course.id == RecordPb.course_id)
            .where(
                RecordPb.scope == scope,
                RecordPb.steamid64 == steamid64,
                RecordPb.type == record_type,
                course.stage == stage,
            )
            .order_by(
                course.map_id.asc(),
                course.stage.asc(),
                RecordPb.time.asc(),
                RecordPb.record_uuid.asc(),
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
    sort_by: RecordPbSortBy = "time",
    sort_order: Literal["asc", "desc"] | None = None,
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
    public_raw_rating_contribution = case(
        (active_ban_exists_clause(steamid64_column=col(Record.steamid64)), 0),
        else_=anchor_pb.raw_rating_contribution,
    )
    sort_expressions = {
        "time": anchor_pb.time,
        "points": public_scoped_points,
        "raw_rating_contribution": public_raw_rating_contribution,
        "created_at": Record.created_at,
        "updated_at": Record.updated_at,
    }

    def _ordered_primary_expression() -> Any:
        direction = sort_order
        if direction is None:
            direction = "asc" if sort_by == "time" else "desc"
        expression = sort_expressions[sort_by]
        return expression.asc() if direction == "asc" else expression.desc()

    def _map_anchor_order_by() -> tuple[Any, ...]:
        if sort_by == "time" and sort_order is None:
            return (anchor_pb.time.asc(), anchor_pb.record_uuid.asc())
        return (
            _ordered_primary_expression(),
            anchor_pb.time.asc(),
            anchor_pb.record_uuid.asc(),
        )

    def _player_anchor_order_by(course: Any) -> tuple[Any, ...]:
        if sort_by == "time" and sort_order is None:
            return (
                course.map_id.asc(),
                course.stage.asc(),
                anchor_pb.time.asc(),
                anchor_pb.record_uuid.asc(),
            )
        return (
            _ordered_primary_expression(),
            course.map_id.asc(),
            course.stage.asc(),
            anchor_pb.time.asc(),
            anchor_pb.record_uuid.asc(),
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
            ServerGroup.id.label("server_group_id"),
            ServerGroup.name.label("server_group_name"),
            ServerGroup.custom_id.label("server_group_custom_id"),
            Record.map_id,
            Map.name.label("map_name"),
            Map.workshop_id.label("workshop_id"),
            Map.difficulty,
            Record.mode,
            Mode.name_short,
            Record.stage,
            anchor_pb.time,
            Record.teleports,
            public_scoped_points.label("points"),
            public_raw_rating_contribution.label("raw_rating_contribution"),
            Record.created_at,
            Record.updated_at,
            Record.updated_by,
            Record.replay_id,
            Record.is_valid,
        )
        .select_from(anchor_pb)
        .join(Record, Record.uuid == anchor_pb.record_uuid)
        .join(Player, col(Record.steamid64) == col(Player.steamid64))
        .join(ServerGlobalapi, col(Record.server_id) == col(ServerGlobalapi.id))
        .outerjoin(ServerGroup, col(ServerGlobalapi.group_id) == col(ServerGroup.id))
        .join(Map, col(Record.map_id) == col(Map.id))
        .join(Mode, col(Record.mode) == col(Mode.name_short))
        .where(Map.validated.is_(True))
        .outerjoin(
            pro_pb,
            and_(
                pro_pb.record_uuid == Record.uuid,
                pro_pb.scope == scope,
                pro_pb.type == RecordType.PRO,
            ),
        )
        .outerjoin(
            ovr_pb,
            and_(
                ovr_pb.record_uuid == Record.uuid,
                ovr_pb.scope == scope,
                ovr_pb.type == RecordType.NUB,
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
            anchor_pb.type == record_type,
        )
        if steamid64 is not None:
            statement = statement.where(anchor_pb.steamid64 == steamid64)
        statement = statement.order_by(*_map_anchor_order_by())
    elif steamid64 is not None:
        course = aliased(MapCourse)
        statement = (
            statement.join(course, course.id == anchor_pb.course_id)
            .where(
                anchor_pb.scope == scope,
                anchor_pb.steamid64 == steamid64,
                anchor_pb.type == record_type,
                course.stage == stage,
            )
            .order_by(*_player_anchor_order_by(course))
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
                _server_group_id,
                _server_group_name,
                _server_group_custom_id,
                record_map_id,
                _map_name,
                _workshop_id,
                _map_tier,
                _record_mode_id,
                _mode_name,
                record_stage,
                _record_time,
                _record_teleports,
                _points,
                _raw_rating_contribution,
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
            server_group=_to_server_group_summary_from_values(
                group_id=server_group_id,
                group_name=server_group_name,
                group_custom_id=server_group_custom_id,
            ),
            map_id=record_map_id,
            map_name=map_name,
            workshop_id=workshop_id,
            map_tier=tiers_by_course[(record_map_id, record_stage)],
            mode_id=record_mode.mode_id,
            mode=mode_name.value,
            stage=record_stage,
            tickrate=128,
            time=float(record_time),
            teleports=record_teleports,
            points=points,
            raw_rating_contribution=raw_rating_contribution,
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
            server_group_id,
            server_group_name,
            server_group_custom_id,
            record_map_id,
            map_name,
            workshop_id,
            map_tier,
            record_mode,
            mode_name,
            record_stage,
            record_time,
            record_teleports,
            points,
            raw_rating_contribution,
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
    counts_statement = (
        select(
            RecordPb.type.label("type"),
            func.count().label("count"),
        )
        .select_from(RecordPb)
        .where(
            col(RecordPb.scope) == scope,
            col(RecordPb.course_id) == course.id,
        )
        .group_by(RecordPb.type)
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
        result_record_type: int(result_count or 0)
        for result_record_type, result_count in (await session.exec(counts_statement)).all()
    }
    unique_nub_finishes = counts_by_type.get(RecordType.NUB, 0)
    unique_pro_finishes = counts_by_type.get(RecordType.PRO, 0)
    total_count = counts_by_type.get(record_type, 0)

    anchor_pb = aliased(RecordPb)
    pro_pb = aliased(RecordPb)
    ovr_pb = aliased(RecordPb)
    scoped_points = pro_pb.points if record_type.is_pro else func.coalesce(ovr_pb.points, 0)
    public_scoped_points = case(
        (active_ban_exists_clause(steamid64_column=col(Record.steamid64)), 0),
        else_=scoped_points,
    )
    public_raw_rating_contribution = case(
        (active_ban_exists_clause(steamid64_column=col(Record.steamid64)), 0),
        else_=anchor_pb.raw_rating_contribution,
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
            ServerGroup.id.label("server_group_id"),
            ServerGroup.name.label("server_group_name"),
            ServerGroup.custom_id.label("server_group_custom_id"),
            Record.map_id,
            Map.name.label("map_name"),
            Map.workshop_id.label("workshop_id"),
            Map.difficulty,
            Record.mode,
            Mode.name_short,
            Record.stage,
            anchor_pb.time,
            Record.teleports,
            public_scoped_points.label("points"),
            public_raw_rating_contribution.label("raw_rating_contribution"),
            Record.created_at,
            Record.updated_at,
            Record.updated_by,
            Record.replay_id,
            Record.is_valid,
        )
        .select_from(anchor_pb)
        .join(Record, Record.uuid == anchor_pb.record_uuid)
        .join(Player, col(Record.steamid64) == col(Player.steamid64))
        .join(ServerGlobalapi, col(Record.server_id) == col(ServerGlobalapi.id))
        .outerjoin(ServerGroup, col(ServerGlobalapi.group_id) == col(ServerGroup.id))
        .join(Map, col(Record.map_id) == col(Map.id))
        .join(Mode, col(Record.mode) == col(Mode.name_short))
        .outerjoin(
            pro_pb,
            and_(
                pro_pb.record_uuid == Record.uuid,
                pro_pb.scope == scope,
                pro_pb.type == RecordType.PRO,
            ),
        )
        .outerjoin(
            ovr_pb,
            and_(
                ovr_pb.record_uuid == Record.uuid,
                ovr_pb.scope == scope,
                ovr_pb.type == RecordType.NUB,
            ),
        )
        .where(
            anchor_pb.scope == scope,
            anchor_pb.course_id == course.id,
            anchor_pb.type == record_type,
        )
        .order_by(anchor_pb.time.asc(), anchor_pb.record_uuid.asc())
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
                _server_group_id,
                _server_group_name,
                _server_group_custom_id,
                record_map_id,
                _map_name,
                _workshop_id,
                _map_tier,
                _record_mode_id,
                _mode_name,
                record_stage,
                _record_time,
                _record_teleports,
                _points,
                _raw_rating_contribution,
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
            server_group=_to_server_group_summary_from_values(
                group_id=server_group_id,
                group_name=server_group_name,
                group_custom_id=server_group_custom_id,
            ),
            map_id=record_map_id,
            map_name=map_name,
            workshop_id=workshop_id,
            map_tier=tiers_by_course[(record_map_id, record_stage)],
            mode_id=record_mode.mode_id,
            mode=mode_name.value,
            stage=record_stage,
            tickrate=128,
            time=float(record_time),
            teleports=record_teleports,
            points=points,
            raw_rating_contribution=raw_rating_contribution,
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
            server_group_id,
            server_group_name,
            server_group_custom_id,
            record_map_id,
            map_name,
            workshop_id,
            map_tier,
            record_mode,
            mode_name,
            record_stage,
            record_time,
            record_teleports,
            points,
            raw_rating_contribution,
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
                .over(order_by=(RecordPb.time.asc(), RecordPb.record_uuid.asc()))
                .label("rank"),
            )
            .select_from(RecordPb)
            .where(
                col(RecordPb.scope) == scope,
                col(RecordPb.course_id) == course.id,
                col(RecordPb.type) == record_type,
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
            col(RecordPb.type) == record_type,
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
                    RecordPb.time.asc(),
                    RecordPb.record_uuid.asc(),
                ),
            )
            .label("rank"),
            func.count()
            .over(partition_by=RecordPb.course_id)
            .label("total_count"),
        )
        .select_from(RecordPb)
        .where(
            col(RecordPb.scope) == scope,
            col(RecordPb.type) == record_type,
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
    use_gokz_top_points: bool,
    offset: int,
    limit: int,
) -> list[tuple[Record, int]]:
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
    else:
        player_ids = []

    if resolved_map_id is not None or steamid64 is not None or player_ids:
        return await _get_pb_records_v0(
            session,
            map_id=resolved_map_id,
            stage=stage,
            steamid64=steamid64,
            steamid64s=player_ids if steamid64 is None else None,
            mode_ids=mode_ids,
            teleports_type=teleports_type,
            server_ids=[server_id] if server_id is not None else None,
            exclude_cheaters=exclude_cheaters,
            use_gokz_top_points=use_gokz_top_points,
            offset=offset,
            limit=limit,
        )

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
