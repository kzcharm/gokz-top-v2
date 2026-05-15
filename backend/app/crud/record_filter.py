from collections.abc import Sequence

from sqlalchemy import case, func, or_
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    AdminMapRecordFiltersPublic,
    AdminRecordFilterPublic,
    AdminRecordFilterStagePublic,
    KZMode,
    Map,
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
        tier=record_filter.tier,
        created_on=record_filter.created_at,
        updated_on=record_filter.updated_at,
        updated_by_id=record_filter.updated_by_id,
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
            col(RecordFilter.mode).in_([legacy_mode_id_to_kz_mode(mode_id) for mode_id in mode_ids])
        )
    if tickrates:
        statement = statement.where(col(RecordFilter.tickrate).in_(tickrates))
    if has_teleports is not None:
        statement = statement.where(col(RecordFilter.has_teleports) == has_teleports)

    statement = statement.order_by(col(RecordFilter.id).asc()).offset(offset).limit(limit)
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
        select(RecordFilter.id)
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


async def load_scoped_course_tiers(
    *,
    session: AsyncSession,
    course_keys: Sequence[tuple[int, int]],
    scope: ModeScope,
) -> dict[tuple[int, int], int]:
    unique_course_keys = list(dict.fromkeys(course_keys))
    if not unique_course_keys:
        return {}

    map_ids = sorted({map_id for map_id, _ in unique_course_keys})
    stages = sorted({stage for _, stage in unique_course_keys})

    map_rows = (
        await session.exec(
            select(Map.id, Map.difficulty).where(col(Map.id).in_(map_ids))
        )
    ).all()
    fallback_difficulty_by_map_id = dict(map_rows)

    scoped_tier_predicate = col(RecordFilter.tier).is_not(None)
    if scope is not ModeScope.VNL:
        scoped_tier_predicate = scoped_tier_predicate & (col(RecordFilter.tier) >= 1)

    scoped_tier_rows = (
        await session.exec(
            select(
                RecordFilter.map_id,
                RecordFilter.stage,
                func.min(RecordFilter.tier).label("tier"),
            )
            .where(
                col(RecordFilter.map_id).in_(map_ids),
                col(RecordFilter.stage).in_(stages),
                col(RecordFilter.tickrate) == 128,
                col(RecordFilter.mode).in_(list(mode_scope_modes(scope))),
                scoped_tier_predicate,
            )
            .group_by(RecordFilter.map_id, RecordFilter.stage)
        )
    ).all()
    scoped_tier_by_course = {
        (map_id, stage): int(tier)
        for map_id, stage, tier in scoped_tier_rows
        if tier is not None
    }

    resolved_tiers: dict[tuple[int, int], int] = {}
    for map_id, stage in unique_course_keys:
        scoped_tier = scoped_tier_by_course.get((map_id, stage))
        if scoped_tier is not None:
            resolved_tiers[(map_id, stage)] = scoped_tier
            continue

        resolved_tiers[(map_id, stage)] = (
            fallback_difficulty_by_map_id.get(map_id, 0) if stage == 0 else 0
        )

    return resolved_tiers


async def load_map_tiers_by_scope(
    *,
    session: AsyncSession,
    map_ids: Sequence[int],
) -> dict[int, MapTiers]:
    unique_map_ids = list(dict.fromkeys(map_ids))
    if not unique_map_ids:
        return {}

    map_rows = (
        await session.exec(
            select(Map.id, Map.difficulty).where(col(Map.id).in_(unique_map_ids))
        )
    ).all()
    fallback_difficulty_by_map_id = dict(map_rows)

    ovr_modes = list(mode_scope_modes(ModeScope.OVR))
    kzt_modes = list(mode_scope_modes(ModeScope.KZT))
    skz_modes = list(mode_scope_modes(ModeScope.SKZ))
    vnl_modes = list(mode_scope_modes(ModeScope.VNL))

    all_modes: list[KZMode] = list(dict.fromkeys([*ovr_modes, *kzt_modes, *skz_modes, *vnl_modes]))
    positive_tier = col(RecordFilter.tier) >= 1

    scoped_tier_rows = (
        await session.exec(
            select(
                RecordFilter.map_id,
                func.min(RecordFilter.tier)
                .filter(
                    col(RecordFilter.mode).in_(ovr_modes),
                    positive_tier,
                )
                .label("ovr_tier"),
                func.min(RecordFilter.tier)
                .filter(
                    col(RecordFilter.mode).in_(kzt_modes),
                    positive_tier,
                )
                .label("kzt_tier"),
                func.min(RecordFilter.tier)
                .filter(
                    col(RecordFilter.mode).in_(skz_modes),
                    positive_tier,
                )
                .label("skz_tier"),
                func.min(RecordFilter.tier)
                .filter(col(RecordFilter.mode).in_(vnl_modes))
                .label("vnl_tier"),
            )
            .where(
                col(RecordFilter.map_id).in_(unique_map_ids),
                col(RecordFilter.stage) == 0,
                col(RecordFilter.tickrate) == 128,
                col(RecordFilter.mode).in_(all_modes),
                col(RecordFilter.tier).is_not(None),
            )
            .group_by(RecordFilter.map_id)
        )
    ).all()

    scoped_tier_by_map_id = {
        map_id: (
            int(ovr_tier) if ovr_tier is not None else None,
            int(kzt_tier) if kzt_tier is not None else None,
            int(skz_tier) if skz_tier is not None else None,
            int(vnl_tier) if vnl_tier is not None else None,
        )
        for map_id, ovr_tier, kzt_tier, skz_tier, vnl_tier in scoped_tier_rows
    }

    resolved_tiers: dict[int, MapTiers] = {}
    for map_id in unique_map_ids:
        fallback_tier = fallback_difficulty_by_map_id.get(map_id, 0)
        ovr_tier, kzt_tier, skz_tier, vnl_tier = scoped_tier_by_map_id.get(
            map_id, (None, None, None, None)
        )
        has_scoped_tiers = any(
            tier is not None for tier in (ovr_tier, kzt_tier, skz_tier, vnl_tier)
        )
        resolved_tiers[map_id] = MapTiers(
            OVR=fallback_tier if ovr_tier is None and not has_scoped_tiers else ovr_tier,
            KZT=fallback_tier if kzt_tier is None and not has_scoped_tiers else kzt_tier,
            SKZ=fallback_tier if skz_tier is None and not has_scoped_tiers else skz_tier,
            VNL=fallback_tier if vnl_tier is None and not has_scoped_tiers else vnl_tier,
        )

    return resolved_tiers
