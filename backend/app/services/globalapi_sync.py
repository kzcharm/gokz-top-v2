from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import timedelta

import psycopg
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import async_session_maker
from app.models import GlobalApiSyncResult, GlobalApiSyncState, get_datetime_utc
from app.services.globalapi_ban_sync import sync_bans_from_globalapi
from app.services.globalapi_maps_sync import sync_maps_from_globalapi
from app.services.globalapi_record_filter_sync import sync_record_filters_from_globalapi
from app.services.globalapi_record_sync import sync_records_from_globalapi
from app.services.globalapi_server_sync import sync_servers_from_globalapi

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GlobalApiSyncTask:
    task_name: str
    stale_after_seconds: int
    run: Callable[..., Awaitable[GlobalApiSyncResult]]
    schedule_hour_utc: int | None = None
    startup_stale_after_seconds: int | None = None
    failure_retry_after_seconds: int = settings.GLOBALAPI_SYNC_FAILURE_RETRY_SECONDS


GLOBALAPI_SYNC_TASKS: tuple[GlobalApiSyncTask, ...] = (
    GlobalApiSyncTask(
        task_name="maps",
        stale_after_seconds=settings.GLOBALAPI_MAPS_SYNC_STALE_AFTER_SECONDS,
        run=sync_maps_from_globalapi,
        schedule_hour_utc=settings.GLOBALAPI_MAPS_SYNC_HOUR_UTC,
        startup_stale_after_seconds=86_400,
    ),
    GlobalApiSyncTask(
        task_name="servers",
        stale_after_seconds=settings.GLOBALAPI_SERVERS_SYNC_STALE_AFTER_SECONDS,
        run=sync_servers_from_globalapi,
    ),
    GlobalApiSyncTask(
        task_name="bans",
        stale_after_seconds=settings.GLOBALAPI_BANS_SYNC_STALE_AFTER_SECONDS,
        run=sync_bans_from_globalapi,
    ),
    GlobalApiSyncTask(
        task_name="record_filters",
        stale_after_seconds=settings.GLOBALAPI_RECORD_FILTERS_SYNC_STALE_AFTER_SECONDS,
        run=sync_record_filters_from_globalapi,
        schedule_hour_utc=settings.GLOBALAPI_RECORD_FILTERS_SYNC_HOUR_UTC,
        startup_stale_after_seconds=86_400,
    ),
    GlobalApiSyncTask(
        task_name="records",
        stale_after_seconds=settings.GLOBALAPI_RECORDS_SYNC_STALE_AFTER_SECONDS,
        run=sync_records_from_globalapi,
    ),
)

_globalapi_sync_run_lock = asyncio.Lock()
_globalapi_sync_stop_event: asyncio.Event | None = None


def _psycopg_database_uri() -> str:
    return str(settings.SQLALCHEMY_DATABASE_URI).replace(
        "postgresql+psycopg", "postgresql", 1
    )


def _runner_advisory_lock_id() -> int:
    lock_key = "globalapi_sync_runner"
    return int(hashlib.md5(lock_key.encode()).hexdigest()[:15], 16)


def _task_advisory_lock_id(task_name: str) -> int:
    lock_key = f"globalapi_sync_task:{task_name}"
    return int(hashlib.md5(lock_key.encode()).hexdigest()[:15], 16)


@asynccontextmanager
async def _runner_advisory_lock() -> AsyncIterator[bool]:
    lock_id = _runner_advisory_lock_id()
    async with await psycopg.AsyncConnection.connect(
        _psycopg_database_uri(),
        autocommit=True,
    ) as connection:
        async with connection.cursor() as cursor:
            await cursor.execute("SELECT pg_try_advisory_lock(%s)", (lock_id,))
            row = await cursor.fetchone()
        if not row or row[0] is not True:
            yield False
            return

        try:
            yield True
        finally:
            with suppress(Exception):
                async with connection.cursor() as cursor:
                    await cursor.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))


@asynccontextmanager
async def _task_advisory_lock(task_name: str) -> AsyncIterator[bool]:
    lock_id = _task_advisory_lock_id(task_name)
    async with await psycopg.AsyncConnection.connect(
        _psycopg_database_uri(),
        autocommit=True,
    ) as connection:
        async with connection.cursor() as cursor:
            await cursor.execute("SELECT pg_try_advisory_lock(%s)", (lock_id,))
            row = await cursor.fetchone()
        if not row or row[0] is not True:
            yield False
            return

        try:
            yield True
        finally:
            with suppress(Exception):
                async with connection.cursor() as cursor:
                    await cursor.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))


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
    startup: bool,
) -> bool:
    state = await session.get(GlobalApiSyncState, task.task_name)
    now = get_datetime_utc()

    if (
        state is not None
        and state.last_error
        and state.last_completed_at is not None
        and now - state.last_completed_at
        < timedelta(seconds=task.failure_retry_after_seconds)
    ):
        return False

    if startup and task.startup_stale_after_seconds is not None:
        if state is None or state.last_successful_at is None:
            return True
        return now - state.last_successful_at >= timedelta(
            seconds=task.startup_stale_after_seconds
        )

    if task.schedule_hour_utc is not None:
        scheduled_at = now.replace(
            hour=task.schedule_hour_utc,
            minute=0,
            second=0,
            microsecond=0,
        )
        if now < scheduled_at:
            return False
        if state is None or state.last_successful_at is None:
            return True
        return state.last_successful_at < scheduled_at

    if state is None or state.last_successful_at is None:
        return True
    return now - state.last_successful_at >= timedelta(seconds=task.stale_after_seconds)


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
            state.last_warnings = getattr(result, "warnings", 0)
        elif error is not None:
            state.last_error = str(error)
        session.add(state)
        await session.commit()


async def run_globalapi_sync_tasks(
    *,
    only_stale: bool,
    startup: bool = False,
) -> dict[str, GlobalApiSyncResult]:
    if _globalapi_sync_run_lock.locked():
        logger.info("Skipping GlobalAPI sync run because another run is in progress")
        return {}

    results: dict[str, GlobalApiSyncResult] = {}
    async with _globalapi_sync_run_lock:
        async with _runner_advisory_lock() as runner_lock_acquired:
            if not runner_lock_acquired:
                logger.info(
                    "Skipping GlobalAPI sync run because another worker holds the advisory lock",
                )
                return {}

            for task in GLOBALAPI_SYNC_TASKS:
                if only_stale:
                    async with async_session_maker() as session:
                        if not await _task_is_stale(
                            session=session,
                            task=task,
                            startup=startup,
                        ):
                            continue

                try:
                    async with _task_advisory_lock(task.task_name) as lock_acquired:
                        if not lock_acquired:
                            logger.info(
                                "Skipping GlobalAPI sync task %s because another worker holds the advisory lock",
                                task.task_name,
                            )
                            continue

                        await _mark_task_started(task_name=task.task_name)
                        async with async_session_maker() as session:
                            result = await task.run(session=session)
                        await _mark_task_finished(
                            task_name=task.task_name,
                            result=result,
                            error=None,
                        )
                except Exception as exc:
                    logger.exception("GlobalAPI sync task %s failed", task.task_name)
                    await _mark_task_finished(
                        task_name=task.task_name,
                        result=None,
                        error=exc,
                    )
                    continue

                results[task.task_name] = result

    return results


async def run_globalapi_sync_runner_in_app() -> None:
    global _globalapi_sync_stop_event

    stop_event = asyncio.Event()
    _globalapi_sync_stop_event = stop_event

    try:
        await run_globalapi_sync_tasks(only_stale=True, startup=True)
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
