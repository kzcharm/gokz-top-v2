import argparse
import asyncio
import logging
import time
from typing import Any, cast

from sqlalchemy import delete, func, text
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import async_session_maker
from app.crud.recent_wr import (
    RECENT_WR_BACKFILL_TASK_NAME,
    rebuild_recent_wr_events_for_map,
    rebuild_recent_wr_events_for_maps,
)
from app.models import Map, MapCourse, RecentWrEventCache, ScheduledTaskState
from app.models.utils import get_datetime_utc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill recent main-course WRs from 1000-point PB winners.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=25,
        help="Number of main-map courses to commit per transaction.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report pending course counts without scanning record history.",
    )
    parser.add_argument(
        "--reset-progress",
        action="store_true",
        help="Clear the cache and saved cursor before a full rebuild.",
    )
    parser.add_argument(
        "--course-id",
        type=int,
        help="Repair one main-map course without changing backfill progress.",
    )
    return parser


async def _get_or_create_state(session: AsyncSession) -> ScheduledTaskState:
    state = await session.get(ScheduledTaskState, RECENT_WR_BACKFILL_TASK_NAME)
    if state is None:
        state = ScheduledTaskState(task_name=RECENT_WR_BACKFILL_TASK_NAME)
        session.add(state)
        await session.flush()
    return state


def _eligible_courses_statement(*, after_course_id: int | None = None) -> Any:
    statement = (
        select(MapCourse.id, MapCourse.map_id)
        .join(Map, col(Map.id) == col(MapCourse.map_id))
        .where(col(MapCourse.stage) == 0, col(Map.validated).is_(True))
        .order_by(col(MapCourse.id).asc())
    )
    if after_course_id is not None:
        statement = statement.where(col(MapCourse.id) > after_course_id)
    return statement


async def _main_async(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    if args.batch_size < 1:
        raise ValueError("--batch-size must be at least 1")
    if args.course_id is not None and args.course_id < 1:
        raise ValueError("--course-id must be at least 1")
    if args.dry_run and args.reset_progress:
        raise ValueError("--dry-run and --reset-progress cannot be combined")

    started = time.monotonic()
    async with async_session_maker() as session:
        lock_acquired = bool(
            (
                await session.exec(
                    cast(
                        Any,
                        text("SELECT pg_try_advisory_lock(hashtext(:task_name))"),
                    ),
                    params={"task_name": RECENT_WR_BACKFILL_TASK_NAME},
                )
            ).one()
        )
        if not lock_acquired:
            raise RuntimeError("Another recent WR backfill is already running")

        try:
            state = await _get_or_create_state(session)
            if args.course_id is not None:
                course = (
                    await session.exec(
                        _eligible_courses_statement().where(
                            col(MapCourse.id) == args.course_id
                        )
                    )
                ).first()
                if course is None:
                    raise ValueError("Course is not a validated main-map course")
                if args.dry_run:
                    logger.info("Would repair course_id=%s", args.course_id)
                    return
                result = await rebuild_recent_wr_events_for_map(
                    session=session,
                    map_id=course[1],
                    notify=True,
                )
                await session.commit()
                logger.info(
                    "Repaired course_id=%s inserted=%s updated=%s deleted=%s elapsed=%.2fs",
                    args.course_id,
                    result.inserted,
                    result.updated,
                    result.deleted,
                    time.monotonic() - started,
                )
                return

            if args.reset_progress:
                await session.exec(delete(RecentWrEventCache))
                state.cursor = None
                state.last_successful_at = None
                state.last_error = None
                state.last_processed = 0
                state.last_created = 0
                state.last_updated = 0
                state.last_errors = 0
                await session.commit()

            state = await _get_or_create_state(session)
            pending_statement = _eligible_courses_statement(
                after_course_id=state.cursor
            ).subquery()
            pending = int(
                (
                    await session.exec(
                        select(func.count()).select_from(pending_statement)
                    )
                ).one()
            )
            if args.dry_run:
                logger.info(
                    "Recent WR backfill cursor=%s pending_courses=%s",
                    state.cursor,
                    pending,
                )
                return

            if state.last_started_at is None and state.cursor is None:
                await session.exec(delete(RecentWrEventCache))
                await session.commit()

            state.last_started_at = get_datetime_utc()
            state.last_completed_at = None
            state.last_error = None
            session.add(state)
            await session.commit()

            processed = 0
            inserted = 0
            updated = 0
            deleted = 0
            while True:
                courses = (
                    await session.exec(
                        _eligible_courses_statement(after_course_id=state.cursor).limit(
                            args.batch_size
                        )
                    )
                ).all()
                if not courses:
                    break

                result = await rebuild_recent_wr_events_for_maps(
                    session=session,
                    map_ids=sorted({map_id for _course_id, map_id in courses}),
                )
                processed += len(courses)
                inserted += result.inserted
                updated += result.updated
                deleted += result.deleted
                state.cursor = courses[-1][0]

                state.last_processed = processed
                state.last_created = inserted
                state.last_updated = updated
                session.add(state)
                await session.commit()
                logger.info(
                    "Recent WR backfill progress cursor=%s processed=%s/%s inserted=%s updated=%s deleted=%s elapsed=%.2fs",
                    state.cursor,
                    processed,
                    pending,
                    inserted,
                    updated,
                    deleted,
                    time.monotonic() - started,
                )

            finished_at = get_datetime_utc()
            state.last_completed_at = finished_at
            state.last_successful_at = finished_at
            state.last_error = None
            session.add(state)
            await session.commit()
            logger.info(
                "Recent WR backfill complete processed=%s inserted=%s updated=%s deleted=%s elapsed=%.2fs",
                processed,
                inserted,
                updated,
                deleted,
                time.monotonic() - started,
            )
        except Exception as error:
            await session.rollback()
            state = await _get_or_create_state(session)
            state.last_completed_at = get_datetime_utc()
            state.last_error = str(error)
            state.last_errors += 1
            session.add(state)
            await session.commit()
            raise
        finally:
            await session.exec(
                cast(
                    Any,
                    text("SELECT pg_advisory_unlock(hashtext(:task_name))"),
                ),
                params={"task_name": RECENT_WR_BACKFILL_TASK_NAME},
            )


def main(argv: list[str] | None = None) -> None:
    asyncio.run(_main_async(argv))


if __name__ == "__main__":
    main()
