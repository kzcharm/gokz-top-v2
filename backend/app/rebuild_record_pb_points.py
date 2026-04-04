import argparse
import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from sqlmodel import col, select

from app import crud
from app.core.db import async_session_maker
from app.models import Map, MapCourse, RecordScope, RecordScopeId

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CoursePointsPlan:
    course_id: int
    map_name: str
    stage: int

    @property
    def label(self) -> str:
        return f"map={self.map_name} stage={self.stage} course_id={self.course_id}"


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
        description="Rebuild exact record_pb points for selected courses.",
    )
    parser.add_argument(
        "--map-name",
        action="append",
        dest="map_names",
        help=(
            "Optional map-name filter. Repeat to rebuild multiple maps. "
            "If omitted, rebuild all maps."
        ),
    )
    parser.add_argument(
        "--stage",
        type=int,
        default=None,
        help=(
            "Optional stage filter. If omitted and --map-name is provided, defaults to 0. "
            "If omitted without --map-name, rebuild all stages."
        ),
    )
    parser.add_argument(
        "--scope",
        action="append",
        choices=[scope.name for scope in RecordScope],
        dest="scopes",
        help="Optional scope filter. Repeat to rebuild multiple scopes. Defaults to all scopes.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit on how many selected courses to process.",
    )
    return parser


def _resolve_scopes(scope_names: Sequence[str] | None) -> tuple[RecordScope, ...]:
    if not scope_names:
        return tuple(RecordScope)
    return tuple(RecordScope[name] for name in scope_names)


def _resolve_stage(*, map_names: Sequence[str] | None, stage: int | None) -> int | None:
    if stage is not None:
        return stage
    if map_names:
        return 0
    return None


async def _load_course_plan(
    *,
    map_names: Sequence[str] | None,
    stage: int | None,
) -> list[CoursePointsPlan]:
    statement = (
        select(MapCourse.id, Map.name, MapCourse.stage)
        .join(Map, col(Map.id) == col(MapCourse.map_id))
        .order_by(col(Map.name).asc(), col(MapCourse.stage).asc(), col(MapCourse.id).asc())
    )
    if map_names:
        statement = statement.where(col(Map.name).in_(list(map_names)))
    if stage is not None:
        statement = statement.where(col(MapCourse.stage) == stage)

    async with async_session_maker() as session:
        rows = (await session.exec(statement)).all()

    return [
        CoursePointsPlan(
            course_id=course_id,
            map_name=map_name,
            stage=course_stage,
        )
        for course_id, map_name, course_stage in rows
    ]


async def _rebuild_course_points(
    *,
    course: CoursePointsPlan,
    scopes: Sequence[RecordScope],
) -> int:
    updated_rows = 0
    async with async_session_maker() as session:
        for scope in scopes:
            scope_id = int(RecordScopeId[scope.name])
            for is_pro_only in (False, True):
                updated = await crud.rebuild_record_pb_points_bucket(
                    session=session,
                    course_id=course.course_id,
                    scope_id=scope_id,
                    is_pro_only=is_pro_only,
                )
                updated_rows += updated
        await session.commit()
    return updated_rows


async def _main_async(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    scopes = _resolve_scopes(args.scopes)
    stage = _resolve_stage(map_names=args.map_names, stage=args.stage)
    courses = await _load_course_plan(map_names=args.map_names, stage=stage)

    if args.limit is not None:
        courses = courses[: args.limit]

    if not courses:
        map_filter = ", ".join(args.map_names) if args.map_names else "*"
        logger.warning("No courses matched filters: map_name=%s stage=%s", map_filter, stage)
        return

    logger.info(
        "Rebuilding exact record_pb points for %s course(s) across %s scope(s)",
        len(courses),
        len(scopes),
    )

    tqdm = _get_tqdm()
    total_updated = 0
    progress = tqdm(
        courses,
        total=len(courses),
        desc="record_pb point courses",
        unit="course",
    )
    for course in progress:
        updated_rows = await _rebuild_course_points(course=course, scopes=scopes)
        total_updated += updated_rows
        progress.set_postfix_str(f"{course.label} updated={updated_rows}")

    logger.info(
        "Finished rebuilding record_pb points for %s course(s); updated rows=%s",
        len(courses),
        total_updated,
    )


def main(argv: list[str] | None = None) -> None:
    asyncio.run(_main_async(argv))


if __name__ == "__main__":
    main()
