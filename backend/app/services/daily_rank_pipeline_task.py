from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.core.db import async_session_maker
from app.models import (
    Record,
    RecordPb,
    RecordType,
    ScheduledTaskResult,
    ScheduledTaskState,
    get_datetime_utc,
)
from app.services.player_friends import sync_player_friends

logger = logging.getLogger(__name__)

TASK_NAME = "daily_rank_pipeline"
STEAM_FETCH_BATCH_SIZE = 4

_daily_rank_pipeline_run_lock = asyncio.Lock()
_daily_rank_pipeline_stop_event: asyncio.Event | None = None


@dataclass(frozen=True, slots=True)
class DailyRankSelection:
    window_start: datetime
    window_end: datetime
    pb_row_count: int
    point_buckets: list[tuple[int, int, RecordType]]
    leaderboard_keys: list[tuple[int, int]]
    map_leaderboard_keys: list[tuple[int, int]]
    map_stat_keys: list[tuple[int, int, RecordType]]
    steamid64s: list[int]


@dataclass(frozen=True, slots=True)
class SteamRefreshResult:
    processed: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0


@dataclass(frozen=True, slots=True)
class FriendRefreshResult:
    processed: int = 0
    synced: int = 0
    rate_limited: int = 0
    private: int = 0
    failed: int = 0


def _current_day_window(now: datetime) -> tuple[datetime, datetime]:
    window_end = now.astimezone(UTC).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    window_start = window_end - timedelta(days=1)
    return window_start, window_end


async def _get_or_create_task_state(
    *,
    session: AsyncSession,
    task_name: str,
) -> ScheduledTaskState:
    state = await session.get(ScheduledTaskState, task_name)
    if state is not None:
        return state

    state = ScheduledTaskState(task_name=task_name)
    session.add(state)
    await session.commit()
    await session.refresh(state)
    return state


async def _task_is_stale(*, session: AsyncSession) -> bool:
    state = await session.get(ScheduledTaskState, TASK_NAME)
    now = get_datetime_utc()
    scheduled_at = now.replace(
        hour=settings.DAILY_RANK_PIPELINE_TASK_HOUR_UTC,
        minute=0,
        second=0,
        microsecond=0,
    )
    if now < scheduled_at:
        return False
    if state is None or state.last_successful_at is None:
        return True
    return state.last_successful_at < scheduled_at


async def _mark_task_started() -> None:
    async with async_session_maker() as session:
        state = await _get_or_create_task_state(session=session, task_name=TASK_NAME)
        state.last_started_at = get_datetime_utc()
        session.add(state)
        await session.commit()


async def _mark_task_finished(
    *,
    result: ScheduledTaskResult | None,
    error: Exception | None,
) -> None:
    async with async_session_maker() as session:
        state = await _get_or_create_task_state(session=session, task_name=TASK_NAME)
        finished_at = get_datetime_utc()
        state.last_completed_at = finished_at
        if result is not None:
            state.last_successful_at = finished_at
            state.last_error = None
            state.last_processed = result.processed
            state.last_created = result.created
            state.last_updated = result.updated
            state.last_errors = result.errors
            state.last_warnings = result.warnings
        elif error is not None:
            state.last_error = str(error)
        session.add(state)
        await session.commit()


def _iter_batches[T](items: Sequence[T], *, batch_size: int) -> list[list[T]]:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    return [
        list(items[index : index + batch_size])
        for index in range(0, len(items), batch_size)
    ]


async def load_daily_rank_selection(*, session: AsyncSession) -> DailyRankSelection:
    now = get_datetime_utc()
    window_start, window_end = _current_day_window(now)
    rows = (
        await session.exec(
            select(
                RecordPb.course_id,
                RecordPb.scope,
                RecordPb.is_pro_only,
                RecordPb.steamid64,
            )
            .join(Record, Record.uuid == RecordPb.record_uuid)
            .where(
                col(Record.created_at) >= window_start,
                col(Record.created_at) < window_end,
            )
            .order_by(
                col(RecordPb.course_id).asc(),
                col(RecordPb.scope).asc(),
                col(RecordPb.is_pro_only).asc(),
                col(RecordPb.steamid64).asc(),
            )
        )
    ).all()

    point_buckets = sorted(
        {
            (course_id, scope.scope_id, RecordType.PRO if is_pro_only else RecordType.NUB)
            for course_id, scope, is_pro_only, _steamid64 in rows
        }
    )
    leaderboard_keys = sorted(
        {
            (scope.scope_id, steamid64)
            for _course_id, scope, _is_pro_only, steamid64 in rows
        }
    )
    steamid64s = sorted(
        {
            steamid64
            for _course_id, _scope_id, _is_pro_only, steamid64 in rows
        }
    )
    map_leaderboard_keys = await crud.load_changed_map_leaderboard_keys(
        session=session,
        window_start=window_start,
        window_end=window_end,
    )
    map_stat_keys = await crud.load_changed_map_stat_keys(
        session=session,
        window_start=window_start,
        window_end=window_end,
    )
    return DailyRankSelection(
        window_start=window_start,
        window_end=window_end,
        pb_row_count=len(rows),
        point_buckets=point_buckets,
        leaderboard_keys=leaderboard_keys,
        map_leaderboard_keys=map_leaderboard_keys,
        map_stat_keys=map_stat_keys,
        steamid64s=steamid64s,
    )


async def rebuild_daily_rank_points(
    *,
    session: AsyncSession,
    selection: DailyRankSelection,
) -> int:
    updated_rows = 0
    for course_id, scope_id, record_type in selection.point_buckets:
        updated_rows += await crud.rebuild_record_pb_points_bucket(
            session=session,
            course_id=course_id,
            scope_id=scope_id,
            record_type=record_type,
        )
    await session.commit()
    return updated_rows


async def rebuild_daily_rank_leaderboards(
    *,
    session: AsyncSession,
    selection: DailyRankSelection,
) -> tuple[int, int]:
    created, updated = await crud.rebuild_leaderboard_players_for_keys(
        session=session,
        keys=selection.leaderboard_keys,
    )
    await session.commit()
    return created, updated


async def rebuild_daily_rank_map_leaderboards(
    *,
    session: AsyncSession,
    selection: DailyRankSelection,
) -> int:
    rebuilt = await crud.rebuild_map_leaderboards_for_keys(
        session=session,
        keys=selection.map_leaderboard_keys,
    )
    await session.commit()
    return rebuilt


async def rebuild_daily_rank_map_stats(
    *,
    session: AsyncSession,
    selection: DailyRankSelection,
) -> int:
    rebuilt = await crud.rebuild_map_stats_for_keys(
        session=session,
        keys=selection.map_stat_keys,
    )
    await session.commit()
    return rebuilt


async def refresh_daily_rank_player_profiles(
    *,
    session: AsyncSession,
    steamid64s: Sequence[int],
) -> SteamRefreshResult:
    if not steamid64s:
        return SteamRefreshResult()

    created = 0
    updated = 0
    skipped = 0
    for batch in _iter_batches(steamid64s, batch_size=STEAM_FETCH_BATCH_SIZE):
        steam_data_by_steamid64 = await crud._fetch_players_from_steam_api(batch)
        for steamid64 in batch:
            player, was_created = (
                await crud.create_or_update_player_from_steam_data_if_fetched(
                    session=session,
                    steamid64=steamid64,
                    steam_data=steam_data_by_steamid64.get(steamid64),
                )
            )
            if player is None:
                skipped += 1
            elif was_created:
                created += 1
            else:
                updated += 1

    return SteamRefreshResult(
        processed=len(steamid64s),
        created=created,
        updated=updated,
        skipped=skipped,
    )


async def refresh_daily_rank_player_friends(
    *,
    session: AsyncSession,
    steamid64s: Sequence[int],
) -> FriendRefreshResult:
    if not steamid64s:
        return FriendRefreshResult()

    synced = 0
    rate_limited = 0
    private = 0
    failed = 0

    for steamid64 in steamid64s:
        player = await crud.get_player_by_steamid64(session=session, steamid64=steamid64)
        if player is None:
            failed += 1
            continue

        result = await sync_player_friends(session=session, player=player)
        if result.kind == "success":
            synced += 1
        elif result.kind == "rate_limited":
            rate_limited += 1
        elif result.kind in {"private_profile", "private_friends"}:
            private += 1
        else:
            failed += 1

    return FriendRefreshResult(
        processed=len(steamid64s),
        synced=synced,
        rate_limited=rate_limited,
        private=private,
        failed=failed,
    )


async def run_daily_rank_pipeline_task(*, only_stale: bool) -> ScheduledTaskResult | None:
    if _daily_rank_pipeline_run_lock.locked():
        logger.info("Skipping daily rank pipeline because another run is in progress")
        return None

    async with _daily_rank_pipeline_run_lock:
        if only_stale:
            async with async_session_maker() as session:
                if not await _task_is_stale(session=session):
                    return None

        await _mark_task_started()
        try:
            async with async_session_maker() as session:
                selection = await load_daily_rank_selection(session=session)
                logger.info(
                    "Daily rank pipeline selected pb_rows=%s buckets=%s leaderboard_keys=%s map_leaderboard_keys=%s map_stat_keys=%s players=%s window_start=%s window_end=%s",
                    selection.pb_row_count,
                    len(selection.point_buckets),
                    len(selection.leaderboard_keys),
                    len(selection.map_leaderboard_keys),
                    len(selection.map_stat_keys),
                    len(selection.steamid64s),
                    selection.window_start.isoformat(),
                    selection.window_end.isoformat(),
                )
                points_updated = await rebuild_daily_rank_points(
                    session=session,
                    selection=selection,
                )
                logger.info(
                    "Daily rank pipeline rebuilt PB points updated_rows=%s",
                    points_updated,
                )
                leaderboard_created, leaderboard_updated = (
                    await rebuild_daily_rank_leaderboards(
                        session=session,
                        selection=selection,
                    )
                )
                logger.info(
                    "Daily rank pipeline rebuilt leaderboard rows created=%s updated=%s",
                    leaderboard_created,
                    leaderboard_updated,
                )
                map_leaderboards_rebuilt = await rebuild_daily_rank_map_leaderboards(
                    session=session,
                    selection=selection,
                )
                logger.info(
                    "Daily rank pipeline rebuilt map leaderboard rows processed=%s",
                    map_leaderboards_rebuilt,
                )
                map_stats_rebuilt = await rebuild_daily_rank_map_stats(
                    session=session,
                    selection=selection,
                )
                logger.info(
                    "Daily rank pipeline rebuilt map stat rows processed=%s",
                    map_stats_rebuilt,
                )
                steam_result = await refresh_daily_rank_player_profiles(
                    session=session,
                    steamid64s=selection.steamid64s,
                )
                logger.info(
                    "Daily rank pipeline refreshed Steam profiles processed=%s created=%s updated=%s skipped=%s",
                    steam_result.processed,
                    steam_result.created,
                    steam_result.updated,
                    steam_result.skipped,
                )
                friend_result = await refresh_daily_rank_player_friends(
                    session=session,
                    steamid64s=selection.steamid64s,
                )
                logger.info(
                    "Daily rank pipeline refreshed player friends processed=%s synced=%s rate_limited=%s private=%s failed=%s",
                    friend_result.processed,
                    friend_result.synced,
                    friend_result.rate_limited,
                    friend_result.private,
                    friend_result.failed,
                )
        except Exception as exc:
            logger.exception("Daily rank pipeline failed")
            await _mark_task_finished(result=None, error=exc)
            return None

        result = ScheduledTaskResult(
            processed=selection.pb_row_count,
            created=leaderboard_created + steam_result.created,
            updated=(
                points_updated
                + leaderboard_updated
                + map_leaderboards_rebuilt
                + map_stats_rebuilt
                + steam_result.updated
                + friend_result.synced
            ),
            errors=0,
            warnings=(
                steam_result.skipped
                + friend_result.rate_limited
                + friend_result.private
                + friend_result.failed
            ),
        )
        await _mark_task_finished(result=result, error=None)
        return result


async def run_daily_rank_pipeline_runner_in_app() -> None:
    global _daily_rank_pipeline_stop_event

    stop_event = asyncio.Event()
    _daily_rank_pipeline_stop_event = stop_event

    try:
        await run_daily_rank_pipeline_task(only_stale=True)
        while True:
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=settings.TASK_RUNNER_POLL_SECONDS,
                )
                return
            except TimeoutError:
                await run_daily_rank_pipeline_task(only_stale=True)
    finally:
        _daily_rank_pipeline_stop_event = None


async def stop_daily_rank_pipeline_runner(task: asyncio.Task[None] | None) -> None:
    if _daily_rank_pipeline_stop_event is not None:
        _daily_rank_pipeline_stop_event.set()
    if task is None:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
