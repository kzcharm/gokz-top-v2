from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import timedelta

from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.core.db import async_session_maker
from app.models import (
    ScheduledTaskResult,
    ScheduledTaskState,
    get_datetime_utc,
)

logger = logging.getLogger(__name__)

TASK_NAME = "leaderboard_player"
DEFAULT_LOOKBACK = timedelta(hours=24)

_leaderboard_player_run_lock = asyncio.Lock()
_leaderboard_player_stop_event: asyncio.Event | None = None


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
        hour=settings.LEADERBOARD_PLAYER_TASK_HOUR_UTC,
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


async def rebuild_changed_leaderboard_players(
    *,
    session: AsyncSession,
) -> ScheduledTaskResult:
    state = await session.get(ScheduledTaskState, TASK_NAME)
    now = get_datetime_utc()
    window_start = (
        state.last_successful_at
        if state is not None and state.last_successful_at is not None
        else now - DEFAULT_LOOKBACK
    )

    keys = await crud.load_changed_leaderboard_player_keys(
        session=session,
        window_start=window_start,
    )
    created, updated = await crud.rebuild_leaderboard_players_for_keys(
        session=session,
        keys=keys,
    )
    await session.commit()
    return ScheduledTaskResult(
        processed=len(keys),
        created=created,
        updated=updated,
        errors=0,
    )


async def run_leaderboard_player_task(*, only_stale: bool) -> ScheduledTaskResult | None:
    if _leaderboard_player_run_lock.locked():
        logger.info("Skipping leaderboard player task because another run is in progress")
        return None

    async with _leaderboard_player_run_lock:
        if only_stale:
            async with async_session_maker() as session:
                if not await _task_is_stale(session=session):
                    return None

        await _mark_task_started()
        try:
            async with async_session_maker() as session:
                result = await rebuild_changed_leaderboard_players(session=session)
        except Exception as exc:
            logger.exception("Leaderboard player task failed")
            await _mark_task_finished(result=None, error=exc)
            return None

        await _mark_task_finished(result=result, error=None)
        return result


async def run_leaderboard_player_runner_in_app() -> None:
    global _leaderboard_player_stop_event

    stop_event = asyncio.Event()
    _leaderboard_player_stop_event = stop_event

    try:
        await run_leaderboard_player_task(only_stale=True)
        while True:
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=settings.TASK_RUNNER_POLL_SECONDS,
                )
                return
            except TimeoutError:
                await run_leaderboard_player_task(only_stale=True)
    finally:
        _leaderboard_player_stop_event = None


async def stop_leaderboard_player_runner(task: asyncio.Task[None] | None) -> None:
    if _leaderboard_player_stop_event is not None:
        _leaderboard_player_stop_event.set()
    if task is None:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
