from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import psycopg
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import async_session_maker
from app.models import (
    MapFileDistributionSyncResult,
    ScheduledTaskState,
    get_datetime_utc,
)
from app.services.map_file_distribution import sync_map_files

TASK_NAME = "map_file_distribution"
logger = logging.getLogger(__name__)
_stop_event: asyncio.Event | None = None


def _psycopg_database_uri() -> str:
    return str(settings.SQLALCHEMY_DATABASE_URI).replace(
        "postgresql+psycopg", "postgresql", 1
    )


def _advisory_lock_id() -> int:
    return int(hashlib.md5(f"scheduled_task:{TASK_NAME}".encode()).hexdigest()[:15], 16)


@asynccontextmanager
async def _advisory_lock() -> AsyncIterator[bool]:
    lock_id = _advisory_lock_id()
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


async def _get_or_create_task_state(
    *,
    session: AsyncSession,
) -> ScheduledTaskState:
    state = await session.get(ScheduledTaskState, TASK_NAME)
    if state is not None:
        return state
    state = ScheduledTaskState(task_name=TASK_NAME)
    session.add(state)
    await session.commit()
    await session.refresh(state)
    return state


async def _is_stale(*, session: AsyncSession) -> bool:
    state = await session.get(ScheduledTaskState, TASK_NAME)
    now = get_datetime_utc()
    scheduled_at = now.replace(
        hour=settings.MAP_DISTRIBUTION_HOUR_UTC,
        minute=0,
        second=0,
        microsecond=0,
    )
    if now < scheduled_at:
        return False
    if state is None or state.last_successful_at is None:
        return True
    return state.last_successful_at < scheduled_at


async def _mark_started() -> None:
    async with async_session_maker() as session:
        state = await _get_or_create_task_state(session=session)
        state.last_started_at = get_datetime_utc()
        session.add(state)
        await session.commit()


async def _mark_finished(
    *,
    result: MapFileDistributionSyncResult | None,
    error: Exception | None,
) -> None:
    async with async_session_maker() as session:
        state = await _get_or_create_task_state(session=session)
        finished_at = get_datetime_utc()
        state.last_completed_at = finished_at
        if result is not None:
            state.last_successful_at = finished_at
            state.last_error = None
            state.last_processed = result.processed
            state.last_created = result.downloaded
            state.last_updated = result.uploaded
            state.last_errors = result.errors
            state.last_warnings = result.warnings
        elif error is not None:
            state.last_error = str(error)
        session.add(state)
        await session.commit()


async def run_map_file_distribution_task(
    *,
    only_stale: bool,
    force: bool = False,
) -> MapFileDistributionSyncResult | None:
    if only_stale:
        async with async_session_maker() as session:
            if not await _is_stale(session=session):
                return None

    async with _advisory_lock() as lock_acquired:
        if not lock_acquired:
            logger.info("Skipping map file distribution because another worker holds the lock")
            return None

        await _mark_started()
        try:
            async with async_session_maker() as session:
                result = await sync_map_files(session=session, force=force)
            await _mark_finished(result=result, error=None)
            return result
        except Exception as exc:
            logger.exception("Map file distribution failed")
            await _mark_finished(result=None, error=exc)
            raise


async def run_map_file_distribution_runner() -> None:
    global _stop_event

    stop_event = asyncio.Event()
    _stop_event = stop_event
    try:
        while True:
            try:
                await run_map_file_distribution_task(only_stale=True)
            except Exception:
                logger.exception("Map file distribution runner iteration failed")

            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=settings.TASK_RUNNER_POLL_SECONDS,
                )
                return
            except TimeoutError:
                continue
    finally:
        _stop_event = None


async def stop_map_file_distribution_runner(task: asyncio.Task[None] | None) -> None:
    if _stop_event is not None:
        _stop_event.set()
    if task is None:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
