from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import timedelta

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import async_session_maker
from app.models import GlobalApiSyncResult, GlobalApiSyncState, get_datetime_utc
from app.services.globalapi_record_sync import sync_records_from_globalapi
from app.services.globalapi_server_sync import sync_servers_from_globalapi

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GlobalApiSyncTask:
    task_name: str
    stale_after_seconds: int
    run: Callable[..., Awaitable[GlobalApiSyncResult]]


GLOBALAPI_SYNC_TASKS: tuple[GlobalApiSyncTask, ...] = (
    GlobalApiSyncTask(
        task_name="servers",
        stale_after_seconds=settings.GLOBALAPI_SERVERS_SYNC_STALE_AFTER_SECONDS,
        run=sync_servers_from_globalapi,
    ),
    GlobalApiSyncTask(
        task_name="records",
        stale_after_seconds=settings.GLOBALAPI_RECORDS_SYNC_STALE_AFTER_SECONDS,
        run=sync_records_from_globalapi,
    ),
)

_globalapi_sync_run_lock = asyncio.Lock()
_globalapi_sync_stop_event: asyncio.Event | None = None


async def _get_or_create_sync_state(
    *,
    session: AsyncSession,
    task_name: str,
) -> GlobalApiSyncState:
    state = await session.get(GlobalApiSyncState, task_name)
    if state is not None:
        return state

    state = GlobalApiSyncState(task_name=task_name)
    session.add(state)
    await session.commit()
    await session.refresh(state)
    return state


async def _task_is_stale(
    *,
    session: AsyncSession,
    task: GlobalApiSyncTask,
) -> bool:
    state = await session.get(GlobalApiSyncState, task.task_name)
    if state is None or state.last_successful_at is None:
        return True
    return get_datetime_utc() - state.last_successful_at >= timedelta(
        seconds=task.stale_after_seconds
    )


async def _mark_task_started(*, task_name: str) -> None:
    async with async_session_maker() as session:
        state = await _get_or_create_sync_state(session=session, task_name=task_name)
        state.last_started_at = get_datetime_utc()
        session.add(state)
        await session.commit()


async def _mark_task_finished(
    *,
    task_name: str,
    result: GlobalApiSyncResult | None,
    error: Exception | None,
) -> None:
    async with async_session_maker() as session:
        state = await _get_or_create_sync_state(session=session, task_name=task_name)
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


async def run_globalapi_sync_tasks(
    *,
    only_stale: bool,
) -> dict[str, GlobalApiSyncResult]:
    if _globalapi_sync_run_lock.locked():
        logger.info("Skipping GlobalAPI sync run because another run is in progress")
        return {}

    results: dict[str, GlobalApiSyncResult] = {}
    async with _globalapi_sync_run_lock:
        for task in GLOBALAPI_SYNC_TASKS:
            if only_stale:
                async with async_session_maker() as session:
                    if not await _task_is_stale(session=session, task=task):
                        continue

            await _mark_task_started(task_name=task.task_name)
            try:
                async with async_session_maker() as session:
                    result = await task.run(session=session)
            except Exception as exc:
                logger.exception("GlobalAPI sync task %s failed", task.task_name)
                await _mark_task_finished(
                    task_name=task.task_name,
                    result=None,
                    error=exc,
                )
                continue

            await _mark_task_finished(
                task_name=task.task_name,
                result=result,
                error=None,
            )
            results[task.task_name] = result

    return results


async def run_globalapi_sync_runner_in_app() -> None:
    global _globalapi_sync_stop_event

    stop_event = asyncio.Event()
    _globalapi_sync_stop_event = stop_event

    try:
        await run_globalapi_sync_tasks(only_stale=True)
        while True:
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=settings.GLOBALAPI_SYNC_RUNNER_POLL_SECONDS,
                )
                return
            except TimeoutError:
                await run_globalapi_sync_tasks(only_stale=True)
    finally:
        _globalapi_sync_stop_event = None


async def stop_globalapi_sync_runner(task: asyncio.Task[None] | None) -> None:
    if _globalapi_sync_stop_event is not None:
        _globalapi_sync_stop_event.set()
    if task is None:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
