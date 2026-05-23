from datetime import UTC, datetime

import pytest
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.models import (
    Map,
    MapCourse,
    MapCourseTier,
    ModeScope,
    RecordFilter,
    legacy_mode_id_to_kz_mode,
)

pytestmark = pytest.mark.asyncio


async def _create_record_filter(
    db: AsyncSession,
    *,
    id: int,
    map_id: int,
    stage: int,
    mode_id: int,
    tickrate: int = 128,
    has_teleports: bool = False,
    tier: int | None = None,
) -> None:
    await db.exec(delete(RecordFilter).where(RecordFilter.id == id))
    await db.commit()
    course: MapCourse | None = None
    if map_id > 0 and await db.get(Map, map_id) is not None:
        course = (
            await db.exec(
                select(MapCourse).where(
                    MapCourse.map_id == map_id,
                    MapCourse.stage == stage,
                )
            )
        ).first()
        if course is None:
            course = MapCourse(map_id=map_id, stage=stage)
            db.add(course)
            await db.commit()
            await db.refresh(course)
    db.add(
        RecordFilter(
            id=id,
            map_id=map_id,
            stage=stage,
            mode_id=mode_id,
            tickrate=tickrate,
            has_teleports=has_teleports,
            tier=tier,
            created_on=datetime(2026, 1, 1, tzinfo=UTC),
            updated_on=datetime(2026, 1, 1, tzinfo=UTC),
            updated_by_id="0",
        )
    )
    await db.commit()
    if tier is None or course is None or course.id is None:
        return

    mode = legacy_mode_id_to_kz_mode(mode_id)
    course_tier = await db.get(MapCourseTier, (course.id, mode))
    if course_tier is None:
        db.add(
            MapCourseTier(
                course_id=course.id,
                mode=mode,
                tier=tier,
                updated_by_id="0",
            )
        )
    else:
        positive_tiers = [value for value in (course_tier.tier, tier) if value > 0]
        course_tier.tier = min(positive_tiers) if positive_tiers else 0
        db.add(course_tier)
    await db.commit()


async def _create_map(
    db: AsyncSession,
    *,
    id: int,
    difficulty: int = 5,
) -> None:
    await db.exec(delete(RecordFilter).where(RecordFilter.map_id == id))
    await db.exec(delete(Map).where(Map.id == id))
    await db.commit()
    db.add(
        Map(
            id=id,
            name=f"kz_test_{id}",
            filesize=123456,
            validated=True,
            difficulty=difficulty,
            created_on=datetime(2026, 1, 1, tzinfo=UTC),
            updated_on=datetime(2026, 1, 1, tzinfo=UTC),
            approved_by_steamid64=76561198000000001,
            synced_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    await db.commit()


async def test_record_filter_exists_for_course_mode_prefers_exact_match(
    db: AsyncSession,
) -> None:
    await _create_record_filter(
        db,
        id=981500,
        map_id=-1,
        stage=0,
        mode_id=200,
        has_teleports=False,
    )
    await _create_record_filter(
        db,
        id=981501,
        map_id=981200,
        stage=0,
        mode_id=200,
        has_teleports=False,
    )

    assert await crud.record_filter_exists_for_course_mode(
        session=db,
        map_id=981200,
        stage=0,
        mode_id=200,
        has_teleports=False,
    )


async def test_record_filter_exists_for_course_mode_uses_wildcard_fallback(
    db: AsyncSession,
) -> None:
    await _create_record_filter(
        db,
        id=981510,
        map_id=-1,
        stage=2,
        mode_id=201,
        has_teleports=True,
    )

    assert await crud.record_filter_exists_for_course_mode(
        session=db,
        map_id=981201,
        stage=2,
        mode_id=201,
        has_teleports=True,
    )


async def test_record_filter_exists_for_course_mode_distinguishes_tp_and_pro(
    db: AsyncSession,
) -> None:
    await _create_record_filter(
        db,
        id=981520,
        map_id=981202,
        stage=1,
        mode_id=202,
        has_teleports=False,
    )

    assert await crud.record_filter_exists_for_course_mode(
        session=db,
        map_id=981202,
        stage=1,
        mode_id=202,
        has_teleports=False,
    )
    assert not await crud.record_filter_exists_for_course_mode(
        session=db,
        map_id=981202,
        stage=1,
        mode_id=202,
        has_teleports=True,
    )


async def test_record_filter_exists_for_course_mode_returns_false_when_missing(
    db: AsyncSession,
) -> None:
    assert not await crud.record_filter_exists_for_course_mode(
        session=db,
        map_id=981203,
        stage=5,
        mode_id=200,
        has_teleports=False,
    )


async def test_load_map_tiers_by_scope_ignores_zero_vnl_tiers_in_aggregate(
    db: AsyncSession,
) -> None:
    await _create_map(db, id=981300, difficulty=6)
    await _create_record_filter(
        db,
        id=981530,
        map_id=981300,
        stage=0,
        mode_id=200,
        tier=6,
    )
    await _create_record_filter(
        db,
        id=981531,
        map_id=981300,
        stage=0,
        mode_id=202,
        has_teleports=False,
        tier=0,
    )
    await _create_record_filter(
        db,
        id=981532,
        map_id=981300,
        stage=0,
        mode_id=202,
        has_teleports=True,
        tier=0,
    )

    tiers = await crud.load_map_tiers_by_scope(session=db, map_ids=[981300])

    assert tiers[981300].OVR == 6
    assert tiers[981300].KZT == 6
    assert tiers[981300].SKZ == 0
    assert tiers[981300].VNL == 0


async def test_load_scoped_course_tiers_ignores_zero_vnl_tiers_for_ovr_scope(
    db: AsyncSession,
) -> None:
    await _create_map(db, id=981301, difficulty=4)
    await _create_record_filter(
        db,
        id=981540,
        map_id=981301,
        stage=0,
        mode_id=200,
        tier=4,
    )
    await _create_record_filter(
        db,
        id=981541,
        map_id=981301,
        stage=0,
        mode_id=202,
        has_teleports=False,
        tier=0,
    )

    ovr_tiers = await crud.load_scoped_course_tiers(
        session=db,
        course_keys=[(981301, 0)],
        scope=ModeScope.OVR,
    )
    vnl_tiers = await crud.load_scoped_course_tiers(
        session=db,
        course_keys=[(981301, 0)],
        scope=ModeScope.VNL,
    )

    assert ovr_tiers[(981301, 0)] == 4
    assert vnl_tiers[(981301, 0)] == 0
