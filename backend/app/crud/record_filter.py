from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy import case, or_, tuple_
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    AdminCourseTierPublic,
    AdminMapCourseTiersPublic,
    AdminMapCourseTierStagePublic,
    AdminMapRecordFiltersPublic,
    AdminRecordFilterPublic,
    AdminRecordFilterStagePublic,
    KZMode,
    MapCourse,
    MapCourseTier,
    MapTiers,
    ModeScope,
    RecordFilter,
    RecordFilterCompatPublicV0,
    legacy_mode_id_to_kz_mode,
    mode_scope_modes,
)


def to_admin_record_filter_public(
    *, record_filter: RecordFilter
) -> AdminRecordFilterPublic:
    return AdminRecordFilterPublic(
        id=record_filter.id,
        map_id=record_filter.map_id,
        stage=record_filter.stage,
        mode=record_filter.mode,
        has_teleports=record_filter.has_teleports,
        created_on=record_filter.created_at,
        updated_on=record_filter.updated_at,
        updated_by_id=record_filter.updated_by_id,
    )


def to_admin_course_tier_public(
    *,
    course: MapCourse,
    mode: KZMode,
    course_tier: MapCourseTier | None,
) -> AdminCourseTierPublic:
    return AdminCourseTierPublic(
        course_id=course.id or 0,
        map_id=course.map_id,
        stage=course.stage,
        mode=mode,
        tier=course_tier.tier if course_tier is not None else 0,
        created_on=course_tier.created_at if course_tier is not None else None,
        updated_on=course_tier.updated_at if course_tier is not None else None,
        updated_by_id=course_tier.updated_by_id if course_tier is not None else None,
    )


async def read_admin_map_record_filters(
    *, session: AsyncSession, map_id: int
) -> AdminMapRecordFiltersPublic:
    rows = list(
        (
            await session.exec(
                select(RecordFilter)
                .where(
                    col(RecordFilter.map_id) == map_id,
                    col(RecordFilter.tickrate) == 128,
                )
                .order_by(
                    col(RecordFilter.stage).asc(),
                    col(RecordFilter.mode).asc(),
                    col(RecordFilter.has_teleports).asc(),
                    col(RecordFilter.id).asc(),
                )
            )
        ).all()
    )

    stages: list[AdminRecordFilterStagePublic] = []
    filters_by_stage: dict[int, list[AdminRecordFilterPublic]] = {}
    for row in rows:
        filters_by_stage.setdefault(row.stage, []).append(
            to_admin_record_filter_public(record_filter=row)
        )
    for stage, record_filters in filters_by_stage.items():
        stages.append(
            AdminRecordFilterStagePublic(
                stage=stage,
                record_filters=record_filters,
            )
        )

    return AdminMapRecordFiltersPublic(map_id=map_id, stages=stages)


async def read_admin_map_course_tiers(
    *,
    session: AsyncSession,
    map_id: int,
) -> AdminMapCourseTiersPublic:
    courses = list(
        (
            await session.exec(
                select(MapCourse)
                .where(col(MapCourse.map_id) == map_id)
                .order_by(col(MapCourse.stage).asc(), col(MapCourse.id).asc())
            )
        ).all()
    )
    if not courses:
        return AdminMapCourseTiersPublic(map_id=map_id, stages=[])

    course_ids = [course.id for course in courses if course.id is not None]
    tier_rows = (
        await session.exec(
            select(MapCourseTier).where(col(MapCourseTier.course_id).in_(course_ids))
        )
    ).all()
    tiers_by_key = {(row.course_id, row.mode): row for row in tier_rows}

    return AdminMapCourseTiersPublic(
        map_id=map_id,
        stages=[
            AdminMapCourseTierStagePublic(
                stage=course.stage,
                course_id=course.id or 0,
                course_tiers=[
                    to_admin_course_tier_public(
                        course=course,
                        mode=mode,
                        course_tier=tiers_by_key.get((course.id or 0, mode)),
                    )
                    for mode in KZMode
                ],
            )
            for course in courses
        ],
    )


async def read_record_filters_v0(
    *,
    session: AsyncSession,
    offset: int = 0,
    limit: int = 100,
    ids: list[int] | None = None,
    map_ids: list[int] | None = None,
    stages: list[int] | None = None,
    mode_ids: list[int] | None = None,
    tickrates: list[int] | None = None,
    has_teleports: bool | None = None,
) -> list[RecordFilterCompatPublicV0]:
    statement = select(RecordFilter)

    if ids:
        statement = statement.where(col(RecordFilter.id).in_(ids))
    if map_ids:
        statement = statement.where(col(RecordFilter.map_id).in_(map_ids))
    if stages:
        statement = statement.where(col(RecordFilter.stage).in_(stages))
    if mode_ids:
        statement = statement.where(
            col(RecordFilter.mode).in_(
                [legacy_mode_id_to_kz_mode(mode_id) for mode_id in mode_ids]
            )
        )
    if tickrates:
        statement = statement.where(col(RecordFilter.tickrate).in_(tickrates))
    if has_teleports is not None:
        statement = statement.where(col(RecordFilter.has_teleports) == has_teleports)

    statement = (
        statement.order_by(col(RecordFilter.id).asc()).offset(offset).limit(limit)
    )
    rows = list((await session.exec(statement)).all())
    return [
        RecordFilterCompatPublicV0(
            id=row.id,
            map_id=row.map_id,
            stage=row.stage,
            mode_id=row.mode_id,
            tickrate=row.tickrate,
            has_teleports=row.has_teleports,
            created_on=row.created_at,
            updated_on=row.updated_at,
            updated_by_id=row.updated_by_id,
        )
        for row in rows
    ]


async def record_filter_exists_for_course_mode(
    *,
    session: AsyncSession,
    map_id: int,
    stage: int,
    mode_id: int,
    tickrate: int = 128,
    has_teleports: bool,
) -> bool:
    statement = (
        select(col(RecordFilter.id))
        .where(
            col(RecordFilter.stage) == stage,
            col(RecordFilter.mode) == legacy_mode_id_to_kz_mode(mode_id),
            col(RecordFilter.tickrate) == tickrate,
            col(RecordFilter.has_teleports) == has_teleports,
            or_(
                col(RecordFilter.map_id) == map_id,
                col(RecordFilter.map_id) == -1,
            ),
        )
        .order_by(
            case((col(RecordFilter.map_id) == map_id, 0), else_=1),
            col(RecordFilter.id).asc(),
        )
        .limit(1)
    )
    return (await session.exec(statement)).first() is not None


def _aggregate_scope_tier(tiers: Sequence[int]) -> int:
    positive_tiers = [tier for tier in tiers if tier > 0]
    if positive_tiers:
        return min(positive_tiers)
    return 0


async def load_scoped_course_tiers(
    *,
    session: AsyncSession,
    course_keys: Sequence[tuple[int, int]],
    scope: ModeScope,
) -> dict[tuple[int, int], int]:
    unique_course_keys = list(dict.fromkeys(course_keys))
    if not unique_course_keys:
        return {}

    rows = (
        await session.exec(
            select(col(MapCourse.map_id), col(MapCourse.stage), col(MapCourseTier.tier))
            .join(MapCourseTier, col(MapCourseTier.course_id) == col(MapCourse.id))
            .where(
                tuple_(col(MapCourse.map_id), col(MapCourse.stage)).in_(
                    unique_course_keys
                ),
                col(MapCourseTier.mode).in_(list(mode_scope_modes(scope))),
            )
        )
    ).all()
    tiers_by_course: dict[tuple[int, int], list[int]] = defaultdict(list)
    for map_id, stage, tier in rows:
        tiers_by_course[(map_id, stage)].append(int(tier))

    return {
        key: _aggregate_scope_tier(tiers_by_course.get(key, []))
        for key in unique_course_keys
    }


async def load_map_tiers_by_scope(
    *,
    session: AsyncSession,
    map_ids: Sequence[int],
) -> dict[int, MapTiers]:
    unique_map_ids = list(dict.fromkeys(map_ids))
    if not unique_map_ids:
        return {}

    rows = (
        await session.exec(
            select(
                col(MapCourse.map_id),
                col(MapCourseTier.mode),
                col(MapCourseTier.tier),
            )
            .join(MapCourseTier, col(MapCourseTier.course_id) == col(MapCourse.id))
            .where(
                col(MapCourse.map_id).in_(unique_map_ids),
                col(MapCourse.stage) == 0,
            )
        )
    ).all()
    tiers_by_map_id_and_mode = {
        (map_id, mode): int(tier) for map_id, mode, tier in rows
    }

    resolved_tiers: dict[int, MapTiers] = {}
    for map_id in unique_map_ids:
        resolved_tiers[map_id] = MapTiers(
            OVR=_aggregate_scope_tier(
                [
                    tiers_by_map_id_and_mode.get((map_id, mode), 0)
                    for mode in mode_scope_modes(ModeScope.OVR)
                ]
            ),
            KZT=_aggregate_scope_tier(
                [
                    tiers_by_map_id_and_mode.get((map_id, mode), 0)
                    for mode in mode_scope_modes(ModeScope.KZT)
                ]
            ),
            SKZ=_aggregate_scope_tier(
                [
                    tiers_by_map_id_and_mode.get((map_id, mode), 0)
                    for mode in mode_scope_modes(ModeScope.SKZ)
                ]
            ),
            VNL=_aggregate_scope_tier(
                [
                    tiers_by_map_id_and_mode.get((map_id, mode), 0)
                    for mode in mode_scope_modes(ModeScope.VNL)
                ]
            ),
        )

    return resolved_tiers
