import argparse
import asyncio
import logging
import sys
import time
from dataclasses import dataclass

from sqlalchemy import text

from app import crud
from app.core.db import async_session_maker
from app.models import RecordScopeId

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


SCOPE_MODE_VALUES_SQL = """
    VALUES
        (0, 200),
        (0, 201),
        (0, 202),
        (0, 203),
        (1, 200),
        (1, 203),
        (2, 201),
        (3, 202)
"""


@dataclass(frozen=True, slots=True)
class RecordPbBucket:
    scope: int
    course_id: int
    map_id: int
    stage: int
    is_pro_only: bool
    expected_rows: int
    existing_rows: int

    @property
    def scope_name(self) -> str:
        return RecordScopeId(self.scope).name

    @property
    def category_name(self) -> str:
        return "PRO" if self.is_pro_only else "OVR"

    @property
    def label(self) -> str:
        return (
            f"map={self.map_id} stage={self.stage} "
            f"scope={self.scope_name} category={self.category_name}"
        )


@dataclass(frozen=True, slots=True)
class RecordPbCoursePlan:
    course_id: int
    map_id: int
    stage: int
    pending_bucket_count: int
    expected_rows: int

    @property
    def label(self) -> str:
        return (
            f"map={self.map_id} stage={self.stage} "
            f"buckets={self.pending_bucket_count} rows={self.expected_rows:,}"
        )


def _get_tqdm():
    try:
        from tqdm import tqdm
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing dependency 'tqdm'. Run `cd backend && uv sync` first."
        ) from exc
    return tqdm


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rebuild the scope-aware record_pb read model from raw record rows.",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="List the rebuild buckets and exit without mutating record_pb.",
    )
    parser.add_argument(
        "--force-all",
        action="store_true",
        help="Rebuild every bucket, not only buckets whose existing row count differs.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N buckets from the plan.",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Run ANALYZE on map_course and record_pb after the rebuild commits.",
    )
    parser.add_argument(
        "--ensure-map-courses",
        action="store_true",
        help="Backfill missing map_course rows from record before planning the rebuild.",
    )
    return parser


async def _count_map_courses() -> int:
    async with async_session_maker() as session:
        return (await session.exec(text("SELECT COUNT(*) FROM map_course"))).one()[0]


async def _count_record_pb_rows() -> int:
    async with async_session_maker() as session:
        return (await session.exec(text("SELECT COUNT(*) FROM record_pb"))).one()[0]


async def _ensure_map_courses() -> None:
    async with async_session_maker() as session:
        await crud.ensure_map_courses_for_valid_records(session=session)
        await session.commit()


async def _load_bucket_plan(*, force_all: bool) -> list[RecordPbBucket]:
    async with async_session_maker() as session:
        rows = (
            await session.exec(
                text(
                    f"""
                    WITH scope_modes(scope, mode_id) AS (
                        {SCOPE_MODE_VALUES_SQL}
                    ),
                    expected_counts AS (
                        SELECT
                            scope_modes.scope,
                            map_course.id AS course_id,
                            map_course.map_id,
                            map_course.stage,
                            FALSE AS is_pro_only,
                            COUNT(DISTINCT record.steamid64)::bigint AS expected_rows
                        FROM record
                        JOIN map_course
                            ON map_course.map_id = record.map_id
                            AND map_course.stage = record.stage
                        JOIN scope_modes
                            ON scope_modes.mode_id = record.mode_id
                        WHERE record.is_valid = true
                        GROUP BY scope_modes.scope, map_course.id, map_course.map_id, map_course.stage

                        UNION ALL

                        SELECT
                            scope_modes.scope,
                            map_course.id AS course_id,
                            map_course.map_id,
                            map_course.stage,
                            TRUE AS is_pro_only,
                            COUNT(DISTINCT record.steamid64)::bigint AS expected_rows
                        FROM record
                        JOIN map_course
                            ON map_course.map_id = record.map_id
                            AND map_course.stage = record.stage
                        JOIN scope_modes
                            ON scope_modes.mode_id = record.mode_id
                        WHERE record.is_valid = true
                            AND record.teleports = 0
                        GROUP BY scope_modes.scope, map_course.id, map_course.map_id, map_course.stage
                    ),
                    existing_counts AS (
                        SELECT
                            record_pb.scope,
                            record_pb.course_id,
                            record_pb.is_pro_only,
                            COUNT(*)::bigint AS existing_rows
                        FROM record_pb
                        GROUP BY record_pb.scope, record_pb.course_id, record_pb.is_pro_only
                    )
                    SELECT
                        expected_counts.scope,
                        expected_counts.course_id,
                        expected_counts.map_id,
                        expected_counts.stage,
                        expected_counts.is_pro_only,
                        expected_counts.expected_rows,
                        COALESCE(existing_counts.existing_rows, 0)::bigint AS existing_rows
                    FROM expected_counts
                    LEFT JOIN existing_counts
                        ON existing_counts.scope = expected_counts.scope
                        AND existing_counts.course_id = expected_counts.course_id
                        AND existing_counts.is_pro_only = expected_counts.is_pro_only
                    WHERE :force_all
                        OR COALESCE(existing_counts.existing_rows, 0) <> expected_counts.expected_rows
                    ORDER BY
                        expected_counts.map_id,
                        expected_counts.stage,
                        expected_counts.scope,
                        expected_counts.is_pro_only
                    """
                ),
                params={"force_all": force_all},
            )
        ).all()

    return [
        RecordPbBucket(
            scope=scope,
            course_id=course_id,
            map_id=map_id,
            stage=stage,
            is_pro_only=is_pro_only,
            expected_rows=int(expected_rows),
            existing_rows=int(existing_rows),
        )
        for scope, course_id, map_id, stage, is_pro_only, expected_rows, existing_rows in rows
    ]


def _print_bucket_plan(*, buckets: list[RecordPbBucket]) -> None:
    if not buckets:
        sys.stdout.write("No record_pb buckets need rebuilding.\n")
        return

    sys.stdout.write("scope\tcourse_id\tmap_id\tstage\tis_pro_only\texpected_rows\texisting_rows\n")
    for bucket in buckets:
        sys.stdout.write(
            f"{bucket.scope_name}\t"
            f"{bucket.course_id}\t"
            f"{bucket.map_id}\t"
            f"{bucket.stage}\t"
            f"{str(bucket.is_pro_only).lower()}\t"
            f"{bucket.expected_rows}\t"
            f"{bucket.existing_rows}\n"
        )


async def _rebuild_course(course: RecordPbCoursePlan) -> None:
    async with async_session_maker() as session:
        await crud.rebuild_record_pbs_for_course(
            session=session,
            course_id=course.course_id,
            map_id=course.map_id,
            stage=course.stage,
        )
        await session.commit()


def _build_course_plan(*, buckets: list[RecordPbBucket]) -> list[RecordPbCoursePlan]:
    by_course: dict[int, RecordPbCoursePlan] = {}
    for bucket in buckets:
        current = by_course.get(bucket.course_id)
        if current is None:
            by_course[bucket.course_id] = RecordPbCoursePlan(
                course_id=bucket.course_id,
                map_id=bucket.map_id,
                stage=bucket.stage,
                pending_bucket_count=1,
                expected_rows=bucket.expected_rows,
            )
            continue

        by_course[bucket.course_id] = RecordPbCoursePlan(
            course_id=current.course_id,
            map_id=current.map_id,
            stage=current.stage,
            pending_bucket_count=current.pending_bucket_count + 1,
            expected_rows=current.expected_rows + bucket.expected_rows,
        )

    return sorted(
        by_course.values(),
        key=lambda course: (course.map_id, course.stage, course.course_id),
    )


async def _load_all_courses_plan() -> list[RecordPbCoursePlan]:
    async with async_session_maker() as session:
        rows = (
            await session.exec(
                text(
                    """
                    SELECT DISTINCT
                        map_course.id,
                        map_course.map_id,
                        map_course.stage
                    FROM map_course
                    JOIN record
                        ON record.map_id = map_course.map_id
                        AND record.stage = map_course.stage
                    WHERE record.is_valid = true
                    ORDER BY map_course.map_id, map_course.stage, map_course.id
                    """
                )
            )
        ).all()

    return [
        RecordPbCoursePlan(
            course_id=course_id,
            map_id=map_id,
            stage=stage,
            pending_bucket_count=0,
            expected_rows=0,
        )
        for course_id, map_id, stage in rows
    ]


async def _main_async(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    started_at = time.monotonic()

    map_course_count = await _count_map_courses()
    record_pb_count = await _count_record_pb_rows()
    should_ensure_map_courses = args.ensure_map_courses or map_course_count == 0
    if should_ensure_map_courses:
        if map_course_count == 0:
            logger.info("map_course is empty; backfilling from valid records")
        else:
            logger.info("Ensuring map_course contains all valid record courses")
        await _ensure_map_courses()
    else:
        logger.info(
            "Skipping map_course ensure (%s existing rows). Use --ensure-map-courses to force it.",
            f"{map_course_count:,}",
        )

    if args.list_only:
        buckets = await _load_bucket_plan(force_all=args.force_all)
        logger.info("Loaded %s record_pb buckets to process", f"{len(buckets):,}")
        if buckets:
            total_expected_rows = sum(bucket.expected_rows for bucket in buckets)
            logger.info("Expected PB rows across selected buckets: %s", f"{total_expected_rows:,}")
        _print_bucket_plan(buckets=buckets)
        return

    if record_pb_count == 0 and not args.force_all:
        logger.info("record_pb is empty; using fast course-only rebuild plan")
        courses = await _load_all_courses_plan()
    else:
        buckets = await _load_bucket_plan(force_all=args.force_all)
        logger.info("Loaded %s record_pb buckets to process", f"{len(buckets):,}")
        if buckets:
            total_expected_rows = sum(bucket.expected_rows for bucket in buckets)
            logger.info("Expected PB rows across selected buckets: %s", f"{total_expected_rows:,}")
        courses = _build_course_plan(buckets=buckets)

    if args.limit is not None:
        courses = courses[: args.limit]

    logger.info("Loaded %s map courses to process", f"{len(courses):,}")
    tqdm = _get_tqdm()
    progress = tqdm(
        courses,
        total=len(courses),
        desc="record_pb courses",
        unit="course",
    )
    processed_rows = 0
    for course in progress:
        await _rebuild_course(course)
        processed_rows += course.expected_rows
        if course.expected_rows > 0:
            progress.set_postfix_str(
                f"{course.label} cumulative={processed_rows:,}"
            )
        else:
            progress.set_postfix_str(
                f"map={course.map_id} stage={course.stage} course_id={course.course_id}"
            )

    async with async_session_maker() as session:
        after_count = (
            await session.exec(text("SELECT COUNT(*) FROM record_pb"))
        ).one()[0]
        logger.info(
            "Finished record_pb rebuild in %.1fs (rows: %s)",
            time.monotonic() - started_at,
            f"{after_count:,}",
        )
        if args.analyze:
            logger.info("Running ANALYZE on map_course and record_pb")
            await session.exec(text("ANALYZE map_course"))
            await session.exec(text("ANALYZE record_pb"))
            await session.commit()


def main(argv: list[str] | None = None) -> None:
    asyncio.run(_main_async(argv))


if __name__ == "__main__":
    main()
