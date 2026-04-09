from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import timedelta

from sqlalchemy import or_
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

logger = logging.getLogger(__name__)

TASK_NAME = "record_pb_points"
DEFAULT_LOOKBACK = timedelta(hours=24)

_record_pb_points_run_lock = asyncio.Lock()
_record_pb_points_stop_event: asyncio.Event | None = None


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
        hour=settings.RECORD_PB_POINTS_TASK_HOUR_UTC,
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


async def rebuild_changed_record_pb_points(*, session: AsyncSession) -> ScheduledTaskResult:
    state = await session.get(ScheduledTaskState, TASK_NAME)
    now = get_datetime_utc()
    window_start = (
        state.last_successful_at
        if state is not None and state.last_successful_at is not None
        else now - DEFAULT_LOOKBACK
    )

    buckets = (
        await session.exec(
            select(RecordPb.course_id, RecordPb.scope, RecordPb.is_pro_only)
            .join(Record, col(Record.uuid) == col(RecordPb.record_uuid))
            .where(
                or_(
                    col(Record.created_on) >= window_start,
                    col(Record.updated_on) >= window_start,
                )
            )
            .distinct()
            .order_by(
                col(RecordPb.course_id).asc(),
                col(RecordPb.scope).asc(),
                col(RecordPb.is_pro_only).asc(),
            )
        )
    ).all()

    updated_rows = 0
    for course_id, scope_id, is_pro_only in buckets:
        updated_rows += await crud.rebuild_record_pb_points_bucket(
            session=session,
            course_id=course_id,
            scope_id=scope_id,
            record_type=RecordType.PRO if is_pro_only else RecordType.NUB,
        )

    await session.commit()
    return ScheduledTaskResult(
        processed=len(buckets),
        created=0,
        updated=updated_rows,
        errors=0,
    )


async def run_record_pb_points_task(*, only_stale: bool) -> ScheduledTaskResult | None:
    if _record_pb_points_run_lock.locked():
        logger.info("Skipping record PB points task because another run is in progress")
        return None

    async with _record_pb_points_run_lock:
        if only_stale:
            async with async_session_maker() as session:
                if not await _task_is_stale(session=session):
                    return None

        await _mark_task_started()
        try:
            async with async_session_maker() as session:
                result = await rebuild_changed_record_pb_points(session=session)
        except Exception as exc:
            logger.exception("Record PB points task failed")
            await _mark_task_finished(result=None, error=exc)
            return None

        await _mark_task_finished(result=result, error=None)
        return result


async def run_record_pb_points_runner_in_app() -> None:
    global _record_pb_points_stop_event

    stop_event = asyncio.Event()
    _record_pb_points_stop_event = stop_event

    try:
        await run_record_pb_points_task(only_stale=True)
        while True:
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=settings.TASK_RUNNER_POLL_SECONDS,
                )
                return
            except TimeoutError:
                await run_record_pb_points_task(only_stale=True)
    finally:
        _record_pb_points_stop_event = None


async def stop_record_pb_points_runner(task: asyncio.Task[None] | None) -> None:
    if _record_pb_points_stop_event is not None:
        _record_pb_points_stop_event.set()
    if task is None:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
