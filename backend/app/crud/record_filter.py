from collections.abc import Sequence

from sqlalchemy import case, func, or_
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    Map,
    MapTiers,
    RecordFilter,
    RecordScope,
    scope_mode_ids,
    scope_to_id,
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
) -> list[RecordFilter]:
    statement = select(RecordFilter)

    if ids:
        statement = statement.where(col(RecordFilter.id).in_(ids))
    if map_ids:
        statement = statement.where(col(RecordFilter.map_id).in_(map_ids))
    if stages:
        statement = statement.where(col(RecordFilter.stage).in_(stages))
    if mode_ids:
        statement = statement.where(col(RecordFilter.mode_id).in_(mode_ids))
    if tickrates:
        statement = statement.where(col(RecordFilter.tickrate).in_(tickrates))
    if has_teleports is not None:
        statement = statement.where(col(RecordFilter.has_teleports) == has_teleports)

    statement = statement.order_by(col(RecordFilter.id).asc()).offset(offset).limit(limit)
    return list((await session.exec(statement)).all())


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
            col(RecordFilter.mode_id) == mode_id,
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
    scope: RecordScope,
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
                col(RecordFilter.mode_id).in_(
                    list(scope_mode_ids(scope_to_id(scope)))
                ),
                col(RecordFilter.tier).is_not(None),
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

    ovr_mode_ids = list(scope_mode_ids(scope_to_id(RecordScope.OVR)))
    kzt_mode_ids = list(scope_mode_ids(scope_to_id(RecordScope.KZT)))
    skz_mode_ids = list(scope_mode_ids(scope_to_id(RecordScope.SKZ)))
    vnl_mode_ids = list(scope_mode_ids(scope_to_id(RecordScope.VNL)))

    all_mode_ids = sorted({*ovr_mode_ids, *kzt_mode_ids, *skz_mode_ids, *vnl_mode_ids})

    scoped_tier_rows = (
        await session.exec(
            select(
                RecordFilter.map_id,
                func.min(RecordFilter.tier)
                .filter(col(RecordFilter.mode_id).in_(ovr_mode_ids))
                .label("ovr_tier"),
                func.min(RecordFilter.tier)
                .filter(col(RecordFilter.mode_id).in_(kzt_mode_ids))
                .label("kzt_tier"),
                func.min(RecordFilter.tier)
                .filter(col(RecordFilter.mode_id).in_(skz_mode_ids))
                .label("skz_tier"),
                func.min(RecordFilter.tier)
                .filter(col(RecordFilter.mode_id).in_(vnl_mode_ids))
                .label("vnl_tier"),
            )
            .where(
                col(RecordFilter.map_id).in_(unique_map_ids),
                col(RecordFilter.stage) == 0,
                col(RecordFilter.tickrate) == 128,
                col(RecordFilter.mode_id).in_(all_mode_ids),
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
