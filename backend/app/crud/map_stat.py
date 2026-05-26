from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    MapCourse,
    MapStatCache,
    MapStatsPublic,
    MapStatType,
    MapWrGapDistributionBinPublic,
    MapWrGapDistributionContentPublic,
    ModeScope,
    Record,
    RecordPb,
    RecordType,
    get_datetime_utc,
    mode_scope_from_id,
    mode_scope_modes,
    mode_scope_to_id,
)

from .ban import not_active_ban_exists_clause

WR_GAP_BIN_WIDTH = 0.5


def _format_bin_start_label(value: float) -> str:
    normalized = 0.0 if math.isclose(value, 0.0, abs_tol=1e-9) else value
    if math.isclose(normalized, round(normalized), abs_tol=1e-9):
        return str(int(round(normalized)))
    return f"{normalized:.1f}"


def _round_down_to_bin_start(value: float) -> float:
    return round(math.floor(value / WR_GAP_BIN_WIDTH) * WR_GAP_BIN_WIDTH, 6)


def _build_centered_bin_specs(
    *,
    assigned_starts: Sequence[float],
    median_start: float,
) -> list[tuple[float, float, float, str]]:
    min_start = min(assigned_starts)
    max_start = max(assigned_starts)
    radius_steps = max(
        round(abs(min_start - median_start) / WR_GAP_BIN_WIDTH),
        round(abs(max_start - median_start) / WR_GAP_BIN_WIDTH),
    )
    lower_start = round(median_start - radius_steps * WR_GAP_BIN_WIDTH, 6)
    upper_start = round(median_start + radius_steps * WR_GAP_BIN_WIDTH, 6)

    specs: list[tuple[float, float, float, str]] = []
    current_start = lower_start
    while current_start <= upper_start + 1e-9:
        lower_bound = current_start
        upper_bound = round(current_start + WR_GAP_BIN_WIDTH, 6)
        specs.append(
            (
                current_start,
                lower_bound,
                upper_bound,
                _format_bin_start_label(current_start),
            )
        )
        current_start = round(current_start + WR_GAP_BIN_WIDTH, 6)
    return specs


def _empty_wr_gap_distribution(
    *,
    wr_time: float | None = None,
    total_pb_count: int = 0,
) -> MapWrGapDistributionContentPublic:
    return MapWrGapDistributionContentPublic(
        wr_time=wr_time,
        median_wr_gap=None,
        total_pb_count=total_pb_count,
        plotted_pb_count=0,
        bins=[],
    )


def _build_wr_gap_distribution(*, record_times: Sequence[float]) -> MapWrGapDistributionContentPublic:
    total_pb_count = len(record_times)
    if not record_times:
        return _empty_wr_gap_distribution(total_pb_count=0)

    wr_time = min(record_times)
    if not math.isfinite(wr_time) or wr_time <= 0:
        return _empty_wr_gap_distribution(total_pb_count=total_pb_count)

    wr_gaps: list[float] = []
    for record_time in record_times:
        ratio_delta = record_time / wr_time - 1
        if not math.isfinite(ratio_delta) or ratio_delta <= 0:
            continue

        wr_gap = math.log2(ratio_delta)
        if not math.isfinite(wr_gap):
            continue

        wr_gaps.append(wr_gap)

    if not wr_gaps:
        return _empty_wr_gap_distribution(
            wr_time=round(wr_time, 3),
            total_pb_count=total_pb_count,
        )

    plotted_pb_count = len(wr_gaps)
    median_wr_gap = statistics.median(wr_gaps)
    assigned_starts = [_round_down_to_bin_start(wr_gap) for wr_gap in wr_gaps]
    median_start = _round_down_to_bin_start(median_wr_gap)
    bin_specs = _build_centered_bin_specs(
        assigned_starts=assigned_starts,
        median_start=median_start,
    )
    bin_counts_by_start: dict[float, int] = {}
    for start in assigned_starts:
        bin_counts_by_start[start] = bin_counts_by_start.get(start, 0) + 1

    return MapWrGapDistributionContentPublic(
        wr_time=round(wr_time, 3),
        median_wr_gap=round(median_wr_gap, 3),
        total_pb_count=total_pb_count,
        plotted_pb_count=plotted_pb_count,
        bins=[
            MapWrGapDistributionBinPublic(
                label=label,
                lower_bound=lower_bound,
                upper_bound=upper_bound,
                count=bin_counts_by_start.get(start, 0),
            )
            for start, lower_bound, upper_bound, label in bin_specs
        ],
    )


async def _get_stage_zero_course_id(
    *,
    session: AsyncSession,
    map_id: int,
) -> int | None:
    statement = (
        select(MapCourse.id)
        .where(
            col(MapCourse.map_id) == map_id,
            col(MapCourse.stage) == 0,
        )
        .limit(1)
    )
    return (await session.exec(statement)).first()


async def _load_wr_gap_record_times(
    *,
    session: AsyncSession,
    course_id: int,
    scope: ModeScope,
    record_type: RecordType,
) -> list[float]:
    rows = (
        await session.exec(
            select(RecordPb.time)
            .where(
                col(RecordPb.course_id) == course_id,
                col(RecordPb.scope) == scope,
                col(RecordPb.type) == record_type,
                not_active_ban_exists_clause(steamid64_column=col(RecordPb.steamid64)),
            )
            .order_by(col(RecordPb.time).asc(), col(RecordPb.record_uuid).asc())
        )
    ).all()
    return [float(record_time) for record_time in rows]


async def rebuild_map_wr_gap_distribution_stat(
    *,
    session: AsyncSession,
    map_id: int,
    scope: ModeScope,
    record_type: RecordType,
    now: datetime | None = None,
) -> MapStatCache:
    current_now = now or get_datetime_utc()
    course_id = await _get_stage_zero_course_id(session=session, map_id=map_id)
    content = _empty_wr_gap_distribution()
    if course_id is not None:
        record_times = await _load_wr_gap_record_times(
            session=session,
            course_id=course_id,
            scope=scope,
            record_type=record_type,
        )
        content = _build_wr_gap_distribution(record_times=record_times)

    cache_row = MapStatCache(
        map_id=map_id,
        scope=scope,
        record_type=record_type,
        type=MapStatType.WR_GAP_DISTRIBUTION,
        content=content.model_dump(mode="json"),
        updated_at=current_now,
    )
    table = MapStatCache.__table__  # type: ignore[attr-defined]
    statement = (
        pg_insert(table)
        .values(cache_row.model_dump(mode="json"))
        .on_conflict_do_update(
            index_elements=[
                table.c.map_id,
                table.c.scope,
                table.c.record_type,
                table.c.type,
            ],
            set_={
                "content": cache_row.content,
                "updated_at": current_now,
            },
        )
    )
    await session.exec(statement)
    return cache_row


async def rebuild_map_stats_for_keys(
    *,
    session: AsyncSession,
    keys: Sequence[tuple[int, int, RecordType]],
    now: datetime | None = None,
) -> int:
    normalized_keys = list(
        dict.fromkeys(
            (map_id, scope_id, record_type)
            for map_id, scope_id, record_type in keys
            if map_id > 0
        )
    )
    if not normalized_keys:
        return 0

    processed = 0
    current_now = now or get_datetime_utc()
    for map_id, scope_id, record_type in normalized_keys:
        await rebuild_map_wr_gap_distribution_stat(
            session=session,
            map_id=map_id,
            scope=mode_scope_from_id(scope_id),
            record_type=record_type,
            now=current_now,
        )
        processed += 1

    return processed


async def load_changed_map_stat_keys(
    *,
    session: AsyncSession,
    window_start: datetime,
    window_end: datetime,
) -> list[tuple[int, int, RecordType]]:
    rows = (
        await session.exec(
            select(Record.map_id, Record.mode, Record.teleports)
            .where(
                col(Record.stage) == 0,
                col(Record.map_id) > 0,
                col(Record.updated_at) >= window_start,
                col(Record.updated_at) < window_end,
            )
            .order_by(col(Record.map_id).asc(), col(Record.mode).asc(), col(Record.teleports).asc())
        )
    ).all()
    return sorted(
        {
            (
                map_id,
                scope_id,
                RecordType.PRO if teleports == 0 else RecordType.NUB,
            )
            for map_id, mode, teleports in rows
            for scope_id in (
                mode_scope_to_id(scope)
                for scope in ModeScope
                if mode in mode_scope_modes(scope)
            )
        },
        key=lambda value: (value[0], value[1], value[2].value),
    )


def _distribution_from_row(cache_row: MapStatCache | None) -> MapWrGapDistributionContentPublic:
    if cache_row is None:
        return _empty_wr_gap_distribution()
    return MapWrGapDistributionContentPublic.model_validate(cache_row.content)


async def get_or_rebuild_map_stats(
    *,
    session: AsyncSession,
    map_id: int,
    scope: ModeScope,
    now: datetime | None = None,
) -> MapStatsPublic:
    current_now = now or get_datetime_utc()
    requested_types = [RecordType.NUB, RecordType.PRO]
    rows = (
        await session.exec(
            select(MapStatCache).where(
                col(MapStatCache.map_id) == map_id,
                col(MapStatCache.scope) == scope,
                col(MapStatCache.type) == MapStatType.WR_GAP_DISTRIBUTION,
                col(MapStatCache.record_type).in_(requested_types),
            )
        )
    ).all()
    rows_by_record_type = {row.record_type: row for row in rows}

    missing_record_types = [
        record_type
        for record_type in requested_types
        if record_type not in rows_by_record_type
    ]
    if missing_record_types:
        for record_type in missing_record_types:
            rows_by_record_type[record_type] = await rebuild_map_wr_gap_distribution_stat(
                session=session,
                map_id=map_id,
                scope=scope,
                record_type=record_type,
                now=current_now,
            )
        await session.commit()

    updated_at = max(
        rows_by_record_type[record_type].updated_at for record_type in requested_types
    )
    return MapStatsPublic(
        map_id=map_id,
        scope=scope,
        updated_at=updated_at,
        nub_wr_gap_distribution=_distribution_from_row(rows_by_record_type.get(RecordType.NUB)),
        pro_wr_gap_distribution=_distribution_from_row(rows_by_record_type.get(RecordType.PRO)),
    )
