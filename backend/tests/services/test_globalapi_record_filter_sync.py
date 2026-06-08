from datetime import UTC, datetime
from typing import Any

import pytest
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    KZMode,
    Map,
    MapCourse,
    MapCourseTier,
    RecordFilter,
)
from app.services import globalapi_record_filter_sync as record_filter_sync
from app.services.vanilla_tier import VanillaTierEntry

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _stub_vanilla_tier_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _empty_vanilla_tiers(**_: object) -> dict[int, VanillaTierEntry]:
        return {}

    monkeypatch.setattr(
        record_filter_sync,
        "load_vanilla_tiers_by_map_id",
        _empty_vanilla_tiers,
    )


async def _create_map(
    db: AsyncSession,
    *,
    id: int,
    difficulty: int = 5,
) -> Map:
    await db.exec(delete(Map).where(Map.id == id))
    await db.commit()

    map_obj = Map(
        id=id,
        name=f"kz_test_{id}",
        filesize=123456,
        validated=True,
        difficulty=difficulty,
        created_on=datetime(2024, 1, 1, tzinfo=UTC),
        updated_on=datetime(2024, 1, 2, tzinfo=UTC),
        approved_by_steamid64=76561198000000001,
        synced_at=datetime(2024, 1, 3, tzinfo=UTC),
    )
    db.add(map_obj)
    await db.commit()
    await db.refresh(map_obj)
    return map_obj


async def _create_local_record_filter(
    db: AsyncSession,
    *,
    id: int,
    map_id: int = 980200,
    stage: int = 0,
    mode_id: int = 200,
    tickrate: int = 128,
    has_teleports: bool = False,
    tier: int | None = None,
    updated_by_id: str | None = "0",
) -> RecordFilter:
    await db.exec(delete(RecordFilter).where(RecordFilter.id == id))
    await db.commit()

    record_filter = RecordFilter(
        id=id,
        map_id=map_id,
        stage=stage,
        mode_id=mode_id,
        tickrate=tickrate,
        has_teleports=has_teleports,
        tier=tier,
        created_on=datetime(2024, 1, 1, tzinfo=UTC),
        updated_on=datetime(2024, 1, 2, tzinfo=UTC),
        updated_by_id=updated_by_id,
    )
    db.add(record_filter)
    await db.commit()
    await db.refresh(record_filter)
    return record_filter


async def _create_local_course_tier(
    db: AsyncSession,
    *,
    map_id: int,
    stage: int,
    mode: KZMode,
    tier: int,
    updated_by_id: str | None = "0",
) -> MapCourseTier:
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
    assert course.id is not None

    existing = await db.get(MapCourseTier, (course.id, mode))
    if existing is None:
        existing = MapCourseTier(
            course_id=course.id,
            mode=mode,
            tier=tier,
            updated_by_id=updated_by_id,
        )
    else:
        existing.tier = tier
        existing.updated_by_id = updated_by_id
    db.add(existing)
    await db.commit()
    await db.refresh(existing)
    return existing


async def _get_course_tier(
    db: AsyncSession,
    *,
    map_id: int,
    stage: int,
    mode: KZMode,
) -> MapCourseTier | None:
    course = (
        await db.exec(
            select(MapCourse).where(
                MapCourse.map_id == map_id,
                MapCourse.stage == stage,
            )
        )
    ).first()
    if course is None or course.id is None:
        return None
    return await db.get(MapCourseTier, (course.id, mode))


def _payload(
    *,
    id: int,
    map_id: int,
    stage: int,
    mode_id: int,
    tickrate: int = 128,
    has_teleports: bool = False,
    updated_by_id: str | None = "0",
) -> dict[str, Any]:
    return {
        "id": id,
        "map_id": map_id,
        "stage": stage,
        "mode_id": mode_id,
        "tickrate": tickrate,
        "has_teleports": has_teleports,
        "created_on": "2020-10-03T00:07:53",
        "updated_on": "2020-10-03T00:07:53",
        "updated_by_id": updated_by_id,
    }


async def test_sync_record_filters_from_globalapi_syncs_multiple_pages(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _create_map(db, id=981200)
    await _create_map(db, id=981201)

    async def _fake_fetch(
        *,
        client: object | None = None,
        offset: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        del client
        assert limit == 2
        pages = {
            0: [
                _payload(id=981600, map_id=981200, stage=0, mode_id=200),
                _payload(id=981601, map_id=981201, stage=1, mode_id=201),
            ],
            2: [
                _payload(id=981602, map_id=-1, stage=2, mode_id=202),
            ],
        }
        return pages.get(offset, [])

    monkeypatch.setattr(
        record_filter_sync.settings,
        "GLOBALAPI_RECORD_FILTERS_LIMIT",
        2,
    )
    monkeypatch.setattr(record_filter_sync, "fetch_record_filters_from_globalapi", _fake_fetch)

    result = await record_filter_sync.sync_record_filters_from_globalapi(session=db)

    assert result == record_filter_sync.GlobalApiSyncResult(
        processed=3,
        created=3,
        updated=0,
        errors=0,
        warnings=0,
    )
    assert await db.get(RecordFilter, 981600) is not None
    assert await db.get(RecordFilter, 981601) is not None
    wildcard = await db.get(RecordFilter, 981602)
    assert wildcard is not None
    assert wildcard.map_id == -1
    assert (
        await _get_course_tier(
            db,
            map_id=981200,
            stage=0,
            mode=KZMode.KZT,
        )
    ) is None
    assert (
        await _get_course_tier(
            db,
            map_id=981201,
            stage=1,
            mode=KZMode.SKZ,
        )
    ) is None
    assert await _get_course_tier(
        db,
        map_id=981602,
        stage=2,
        mode=KZMode.VNL,
    ) is None


async def test_sync_record_filters_from_globalapi_creates_map_courses_only_for_exact_128_filters(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _create_map(db, id=981205, difficulty=6)

    async def _fake_fetch(
        *,
        client: object | None = None,
        offset: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        del client, limit
        if offset > 0:
            return []
        return [
            _payload(id=981605, map_id=981205, stage=0, mode_id=200, tickrate=128),
            _payload(id=981606, map_id=981205, stage=1, mode_id=200, tickrate=128),
            _payload(id=981607, map_id=981205, stage=2, mode_id=200, tickrate=64),
        ]

    monkeypatch.setattr(record_filter_sync, "fetch_record_filters_from_globalapi", _fake_fetch)

    result = await record_filter_sync.sync_record_filters_from_globalapi(session=db)

    assert result.processed == 3
    main_course = (
        await db.exec(
            select(MapCourse).where(
                MapCourse.map_id == 981205,
                MapCourse.stage == 0,
            )
        )
    ).first()
    bonus_course = (
        await db.exec(
            select(MapCourse).where(
                MapCourse.map_id == 981205,
                MapCourse.stage == 1,
            )
        )
    ).first()
    non_128_course = (
        await db.exec(
            select(MapCourse).where(
                MapCourse.map_id == 981205,
                MapCourse.stage == 2,
            )
        )
    ).first()

    assert main_course is not None
    assert bonus_course is not None
    assert non_128_course is None
    assert await _get_course_tier(
        db,
        map_id=981205,
        stage=0,
        mode=KZMode.KZT,
    ) is None
    assert await db.get(RecordFilter, 981607) is not None


async def test_sync_record_filters_from_globalapi_preserves_existing_non_vnl_course_tier(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _create_map(db, id=981208, difficulty=8)
    await _create_local_course_tier(
        db,
        map_id=981208,
        stage=0,
        mode=KZMode.KZT,
        tier=8,
    )

    async def _fake_fetch(
        *,
        client: object | None = None,
        offset: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        del client, limit
        if offset > 0:
            return []
        return [_payload(id=981608, map_id=981208, stage=0, mode_id=200)]

    monkeypatch.setattr(record_filter_sync, "fetch_record_filters_from_globalapi", _fake_fetch)

    result = await record_filter_sync.sync_record_filters_from_globalapi(session=db)

    assert result.processed == 1
    synced = await _get_course_tier(
        db,
        map_id=981208,
        stage=0,
        mode=KZMode.KZT,
    )
    assert synced is not None
    assert synced.tier == 8


async def test_sync_record_filters_from_globalapi_uses_vanilla_tiers_for_vnl_tp_and_pro(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _create_map(db, id=981260, difficulty=8)

    async def _fake_fetch(
        *,
        client: object | None = None,
        offset: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        del client, limit
        if offset > 0:
            return []
        return [
            _payload(
                id=981660,
                map_id=981260,
                stage=0,
                mode_id=202,
                has_teleports=True,
            ),
            _payload(
                id=981661,
                map_id=981260,
                stage=0,
                mode_id=202,
                has_teleports=False,
            ),
        ]

    async def _fake_vanilla_tiers(**_: object) -> dict[int, VanillaTierEntry]:
        return {
            981260: VanillaTierEntry(tp_tier=3, pro_tier=6),
        }

    monkeypatch.setattr(record_filter_sync, "fetch_record_filters_from_globalapi", _fake_fetch)
    monkeypatch.setattr(record_filter_sync, "load_vanilla_tiers_by_map_id", _fake_vanilla_tiers)

    result = await record_filter_sync.sync_record_filters_from_globalapi(session=db)

    assert result.processed == 2
    course_tier = await _get_course_tier(
        db,
        map_id=981260,
        stage=0,
        mode=KZMode.VNL,
    )
    assert course_tier is not None
    assert course_tier.tier == 3


async def test_sync_record_filters_from_globalapi_sets_zero_tier_for_vnl_status_maps(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _create_map(db, id=981261, difficulty=7)

    async def _fake_fetch(
        *,
        client: object | None = None,
        offset: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        del client, limit
        if offset > 0:
            return []
        return [
            _payload(
                id=981662,
                map_id=981261,
                stage=0,
                mode_id=202,
                has_teleports=False,
            )
        ]

    async def _fake_vanilla_tiers(**_: object) -> dict[int, VanillaTierEntry]:
        return {
            981261: VanillaTierEntry(tp_tier=0, pro_tier=0),
        }

    monkeypatch.setattr(record_filter_sync, "fetch_record_filters_from_globalapi", _fake_fetch)
    monkeypatch.setattr(record_filter_sync, "load_vanilla_tiers_by_map_id", _fake_vanilla_tiers)

    result = await record_filter_sync.sync_record_filters_from_globalapi(session=db)

    assert result.processed == 1
    synced = await _get_course_tier(
        db,
        map_id=981261,
        stage=0,
        mode=KZMode.VNL,
    )
    assert synced is not None
    assert synced.tier == 0


async def test_sync_record_filters_from_globalapi_overrides_existing_vnl_tier(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _create_map(db, id=981262, difficulty=4)
    await _create_local_record_filter(
        db,
        id=981663,
        map_id=981262,
        stage=0,
        mode_id=202,
        has_teleports=False,
        tier=8,
    )
    await _create_local_course_tier(
        db,
        map_id=981262,
        stage=0,
        mode=KZMode.VNL,
        tier=8,
    )

    async def _fake_fetch(
        *,
        client: object | None = None,
        offset: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        del client, limit
        if offset > 0:
            return []
        return [
            _payload(
                id=981663,
                map_id=981262,
                stage=0,
                mode_id=202,
                has_teleports=False,
            )
        ]

    async def _fake_vanilla_tiers(**_: object) -> dict[int, VanillaTierEntry]:
        return {
            981262: VanillaTierEntry(tp_tier=2, pro_tier=5),
        }

    monkeypatch.setattr(record_filter_sync, "fetch_record_filters_from_globalapi", _fake_fetch)
    monkeypatch.setattr(record_filter_sync, "load_vanilla_tiers_by_map_id", _fake_vanilla_tiers)

    result = await record_filter_sync.sync_record_filters_from_globalapi(session=db)

    assert result.processed == 1
    synced = await _get_course_tier(
        db,
        map_id=981262,
        stage=0,
        mode=KZMode.VNL,
    )
    assert synced is not None
    assert synced.tier == 2


async def test_sync_record_filters_from_globalapi_updates_existing_rows(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _create_local_record_filter(
        db,
        id=981610,
        map_id=981210,
        stage=0,
        mode_id=200,
        has_teleports=False,
        tier=5,
    )

    async def _fake_fetch(
        *,
        client: object | None = None,
        offset: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        del client, limit
        if offset > 0:
            return []
        return [
            _payload(
                id=981610,
                map_id=981211,
                stage=3,
                mode_id=201,
                has_teleports=True,
                updated_by_id="76561198000000001",
            )
        ]

    monkeypatch.setattr(record_filter_sync, "fetch_record_filters_from_globalapi", _fake_fetch)

    result = await record_filter_sync.sync_record_filters_from_globalapi(session=db)

    assert result.processed == 1
    assert result.created == 0
    assert result.updated == 1
    synced = await db.get(RecordFilter, 981610)
    assert synced is not None
    assert synced.map_id == 981211
    assert synced.stage == 3
    assert synced.mode_id == 201
    assert synced.has_teleports is True
    assert synced.tier == 5
    assert synced.updated_by_id == "76561198000000001"


async def test_sync_record_filters_from_globalapi_skips_malformed_rows(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_fetch(
        *,
        client: object | None = None,
        offset: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        del client, limit
        if offset > 0:
            return []
        return [
            {
                "id": 981620,
                "map_id": 981220,
                "stage": 0,
                "mode_id": 200,
                "tickrate": 0,
            },
            _payload(id=981621, map_id=981221, stage=0, mode_id=200),
        ]

    monkeypatch.setattr(record_filter_sync, "fetch_record_filters_from_globalapi", _fake_fetch)

    result = await record_filter_sync.sync_record_filters_from_globalapi(session=db)

    assert result.processed == 1
    assert result.created == 1
    assert result.errors == 1
    assert await db.get(RecordFilter, 981620) is None
    assert await db.get(RecordFilter, 981621) is not None


async def test_sync_record_filters_from_globalapi_ignores_duplicate_ids_with_warning(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_fetch(
        *,
        client: object | None = None,
        offset: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        del client, limit
        if offset > 0:
            return []
        return [
            _payload(id=981630, map_id=981230, stage=0, mode_id=200),
            _payload(id=981630, map_id=981231, stage=1, mode_id=201),
        ]

    monkeypatch.setattr(record_filter_sync, "fetch_record_filters_from_globalapi", _fake_fetch)

    result = await record_filter_sync.sync_record_filters_from_globalapi(session=db)

    assert result.processed == 1
    assert result.created == 1
    assert result.warnings == 1
    synced = await db.get(RecordFilter, 981630)
    assert synced is not None
    assert synced.map_id == 981230


async def test_sync_record_filters_from_globalapi_keeps_rows_missing_upstream(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _create_local_record_filter(db, id=981640, map_id=981240, stage=0, mode_id=200)

    async def _fake_fetch(
        *,
        client: object | None = None,
        offset: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        del client, limit
        if offset > 0:
            return []
        return [_payload(id=981641, map_id=981241, stage=0, mode_id=200)]

    monkeypatch.setattr(record_filter_sync, "fetch_record_filters_from_globalapi", _fake_fetch)

    result = await record_filter_sync.sync_record_filters_from_globalapi(session=db)

    assert result.processed == 1
    assert await db.get(RecordFilter, 981640) is not None
    assert await db.get(RecordFilter, 981641) is not None
