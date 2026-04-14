import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlmodel import col, select

from app import crud
from app.core.db import async_session_maker
from app.models import Map, MapCourse, ModeScope, ModeScopeId

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CoursePointsPlan:
    course_id: int
    map_id: int
    map_name: str
    stage: int

    @property
    def label(self) -> str:
        return f"map={self.map_name} stage={self.stage} course_id={self.course_id}"


def _get_tqdm() -> Any:
    try:
        from tqdm import tqdm  # type: ignore[import-untyped]
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing dependency 'tqdm'. Run `cd backend && uv sync` first."
        ) from exc
    return tqdm


def resolve_scopes(scope_names: Sequence[str] | None) -> tuple[ModeScope, ...]:
    if not scope_names:
        return tuple(ModeScope)
    return tuple(ModeScope[name] for name in scope_names)


def resolve_stage(*, stage: int | None, all_stages: bool) -> int | None:
    if stage is not None:
        return stage
    if all_stages:
        return None
    return 0


async def _load_course_plan(
    *,
    map_names: Sequence[str] | None,
    stage: int | None,
) -> list[CoursePointsPlan]:
    statement = (
        select(MapCourse.id, MapCourse.map_id, Map.name, MapCourse.stage)
        .join(Map, col(Map.id) == col(MapCourse.map_id))
        .order_by(col(Map.name).asc(), col(MapCourse.stage).asc(), col(MapCourse.id).asc())
    )
    if map_names:
        statement = statement.where(col(Map.name).in_(list(map_names)))
    if stage is not None:
        statement = statement.where(col(MapCourse.stage) == stage)

    async with async_session_maker() as session:
        rows = (await session.exec(statement)).all()

    courses: list[CoursePointsPlan] = []
    for course_id, map_id, map_name, course_stage in rows:
        if (
            course_id is None
            or map_id is None
            or map_name is None
            or course_stage is None
        ):
            raise RuntimeError("Course rebuild plan returned incomplete row data.")
        courses.append(
            CoursePointsPlan(
                course_id=course_id,
                map_id=map_id,
                map_name=map_name,
                stage=course_stage,
            )
        )
    return courses


async def _load_course_scope_tiers(
    *,
    courses: Sequence[CoursePointsPlan],
    scopes: Sequence[ModeScope],
) -> dict[int, dict[int, int]]:
    if not courses:
        return {}

    course_key_by_id = {
        course.course_id: (course.map_id, course.stage)
        for course in courses
    }
    unique_course_keys = list(course_key_by_id.values())
    tiers_by_course_id: dict[int, dict[int, int]] = {
        course.course_id: {}
        for course in courses
    }

    async with async_session_maker() as session:
        for scope in scopes:
            scope_tiers = await crud.load_scoped_course_tiers(
                session=session,
                course_keys=unique_course_keys,
                scope=scope,
            )
            scope_id = int(ModeScopeId[scope.name])
            for course_id, course_key in course_key_by_id.items():
                tiers_by_course_id[course_id][scope_id] = scope_tiers[course_key]

    return tiers_by_course_id


async def _rebuild_course_points(
    *,
    course: CoursePointsPlan,
    scopes: Sequence[ModeScope],
    tiers_by_scope: dict[int, int],
) -> int:
    async with async_session_maker() as session:
        updated_rows = await crud.rebuild_record_pb_points_for_course(
            session=session,
            course_id=course.course_id,
            scope_ids=[int(ModeScopeId[scope.name]) for scope in scopes],
            tiers_by_scope=tiers_by_scope,
        )
        await session.commit()
    return updated_rows


async def rebuild_record_pb_points(
    *,
    scopes: Sequence[ModeScope],
    map_names: Sequence[str] | None,
    stage: int | None,
    limit: int | None,
) -> int:
    map_name_list = list(map_names) if map_names is not None else None
    courses = await _load_course_plan(map_names=map_name_list, stage=stage)

    if limit is not None:
        courses = courses[:limit]

    if not courses:
        map_filter = ", ".join(map_name_list) if map_name_list else "*"
        logger.warning("No courses matched filters: map_name=%s stage=%s", map_filter, stage)
        return 0

    logger.info(
        "Rebuilding exact record_pb points for %s course(s) across %s scope(s)",
        len(courses),
        len(scopes),
    )
    logger.info("Preloading scoped course tiers for rebuild plan")
    tiers_by_course_id = await _load_course_scope_tiers(courses=courses, scopes=scopes)

    tqdm = _get_tqdm()
    total_updated = 0
    progress = tqdm(
        courses,
        total=len(courses),
        desc="record_pb point courses",
        unit="course",
    )
    for course in progress:
        updated_rows = await _rebuild_course_points(
            course=course,
            scopes=scopes,
            tiers_by_scope=tiers_by_course_id[course.course_id],
        )
        total_updated += updated_rows
        progress.set_postfix_str(f"{course.label} updated={updated_rows}")

    logger.info(
        "Finished rebuilding record_pb points for %s course(s); updated rows=%s",
        len(courses),
        total_updated,
    )
    return total_updated
