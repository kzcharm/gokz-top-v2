from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import KZMode, Map, MapCourse, MapCourseTier, Player
from app.services.globalapi_maps_sync import (
    MAP_DATETIME_FALLBACK,
    _normalize_datetime,
    sync_maps_from_globalapi,
)
from app.services.steam_workshop import SteamWorkshopFileDetails


@pytest.fixture(autouse=True)
def _disable_workshop_author_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _mock_fetch_workshop_file_details(
        *,
        workshop_ids: list[str],
    ) -> dict[str, SteamWorkshopFileDetails]:
        _ = workshop_ids
        return {}

    monkeypatch.setattr(
        "app.services.globalapi_maps_sync.fetch_workshop_file_details",
        _mock_fetch_workshop_file_details,
    )


@pytest_asyncio.fixture(autouse=True)
async def _isolate_map_sync_tables(db: AsyncSession) -> None:
    await db.exec(delete(MapCourseTier))
    existing_maps = (await db.exec(select(Map))).all()
    for map_obj in existing_maps:
        map_obj.validated = False
        db.add(map_obj)
    await db.commit()


@pytest.mark.asyncio
async def test_sync_maps_from_globalapi_upserts_and_normalizes_datetime(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing_id = int(datetime.now(UTC).timestamp()) % 100000 + 920000
    created_id = existing_id + 1

    await db.exec(delete(Map).where(Map.id.in_([existing_id, created_id])))
    await db.commit()

    existing_map = Map(
        id=existing_id,
        name=f"kz_sync_seed_{existing_id}",
        filesize=1,
        validated=False,
        difficulty=1,
        created_on=datetime(2020, 1, 1, tzinfo=UTC),
        updated_on=datetime(2020, 1, 1, tzinfo=UTC),
        approved_by_steamid64=0,
        workshop_id=None,
        synced_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    db.add(existing_map)
    await db.commit()

    sample_payload = [
        {
            "id": existing_id,
            "name": f"kz_sync_existing_{existing_id}",
            "filesize": 58411256,
            "validated": True,
            "difficulty": 5,
            "created_on": "0001-01-01T00:00:00",
            "updated_on": "2021-06-29T00:19:22",
            "approved_by_steamid64": "76561198003275951",
            "workshop_url": "https://steamcommunity.com/sharedfiles/filedetails/?id=1986459033",
        },
        {
            "id": created_id,
            "name": f"kz_sync_created_{created_id}",
            "filesize": 100,
            "validated": False,
            "difficulty": 2,
            "created_on": None,
            "updated_on": "bad",
            "approved_by_steamid64": "0",
            "workshop_url": None,
        },
    ]

    async def _mock_fetch() -> list[dict[str, object]]:
        return sample_payload

    monkeypatch.setattr(
        "app.services.globalapi_maps_sync.fetch_maps_from_globalapi",
        _mock_fetch,
    )

    result = await sync_maps_from_globalapi(session=db)

    assert result.processed == 2
    assert result.created == 1
    assert result.updated == 1
    assert result.errors == 0

    refreshed_200 = await db.get(Map, existing_id)
    assert refreshed_200 is not None
    assert refreshed_200.name == f"kz_sync_existing_{existing_id}"
    assert refreshed_200.difficulty == 5
    assert refreshed_200.created_at == _normalize_datetime("0001-01-01T00:00:00")
    assert refreshed_200.workshop_id == 1986459033

    refreshed_201 = await db.get(Map, created_id)
    assert refreshed_201 is not None
    assert refreshed_201.created_at == _normalize_datetime(MAP_DATETIME_FALLBACK)
    assert refreshed_201.updated_at == _normalize_datetime(MAP_DATETIME_FALLBACK)


@pytest.mark.asyncio
async def test_sync_maps_from_globalapi_preserves_and_appends_author_metadata(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    map_id = int(datetime.now(UTC).timestamp()) % 100000 + 925000
    await db.exec(delete(Map).where(Map.id == map_id))
    await db.commit()
    db.add(
        Map(
            id=map_id,
            name=f"kz_sync_authors_{map_id}",
            filesize=1,
            validated=True,
            difficulty=1,
            created_on=datetime(2020, 1, 1, tzinfo=UTC),
            updated_on=datetime(2020, 1, 1, tzinfo=UTC),
            approved_by_steamid64=0,
            workshop_id=111,
            authors=["76561198000000001"],
            no_steamid_names=["Seeded Name"],
            synced_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
    )
    await db.commit()

    async def _mock_fetch() -> list[dict[str, object]]:
        return [
            {
                "id": map_id,
                "name": f"kz_sync_authors_{map_id}",
                "filesize": 58411256,
                "validated": True,
                "difficulty": 5,
                "created_on": "2021-06-29T00:19:22",
                "updated_on": "2021-06-29T00:19:22",
                "approved_by_steamid64": "76561198003275951",
                "workshop_url": "https://steamcommunity.com/sharedfiles/filedetails/?id=1986459033",
                "authors": ["76561198000000002", "Name From Wrong Field"],
                "no_steamid_names": ["GlobalAPI Name"],
            },
        ]

    async def _mock_fetch_workshop_file_details(
        *,
        workshop_ids: list[str],
    ) -> dict[str, SteamWorkshopFileDetails]:
        assert workshop_ids == ["1986459033"]
        return {
            "1986459033": SteamWorkshopFileDetails(
                publishedfileid="1986459033",
                creator="76561198000000003",
                preview_url=None,
            )
        }

    monkeypatch.setattr(
        "app.services.globalapi_maps_sync.fetch_maps_from_globalapi",
        _mock_fetch,
    )
    monkeypatch.setattr(
        "app.services.globalapi_maps_sync.fetch_workshop_file_details",
        _mock_fetch_workshop_file_details,
    )

    result = await sync_maps_from_globalapi(session=db)

    assert result.processed == 1
    refreshed = await db.get(Map, map_id)
    assert refreshed is not None
    assert refreshed.authors == [
        "76561198000000001",
        "76561198000000002",
        "76561198000000003",
    ]
    assert refreshed.no_steamid_names == [
        "Seeded Name",
        "GlobalAPI Name",
        "Name From Wrong Field",
    ]
    for steamid64 in (
        76561198000000001,
        76561198000000002,
        76561198000000003,
    ):
        author_player = await db.get(Player, steamid64)
        assert author_player is not None
        assert author_player.name == str(steamid64)


@pytest.mark.asyncio
async def test_sync_maps_allows_duplicate_names(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_id = int(datetime.now(UTC).timestamp()) % 100000 + 930000
    first_id = base_id
    second_id = base_id + 1

    await db.exec(delete(Map).where(Map.id.in_([first_id, second_id])))
    await db.commit()

    duplicate_name = f"kz_duplicate_name_{base_id}"
    sample_payload = [
        {
            "id": first_id,
            "name": duplicate_name,
            "filesize": 100,
            "validated": True,
            "difficulty": 3,
            "created_on": "2021-01-01T00:00:00",
            "updated_on": "2021-01-01T00:00:00",
            "approved_by_steamid64": "76561198000000001",
            "workshop_url": "https://steamcommunity.com/sharedfiles/filedetails/?id=111",
        },
        {
            "id": second_id,
            "name": duplicate_name,
            "filesize": 200,
            "validated": False,
            "difficulty": 4,
            "created_on": "2021-01-02T00:00:00",
            "updated_on": "2021-01-02T00:00:00",
            "approved_by_steamid64": "76561198000000002",
            "workshop_url": "https://steamcommunity.com/sharedfiles/filedetails/?id=222",
        },
    ]

    async def _mock_fetch() -> list[dict[str, object]]:
        return sample_payload

    monkeypatch.setattr(
        "app.services.globalapi_maps_sync.fetch_maps_from_globalapi",
        _mock_fetch,
    )

    result = await sync_maps_from_globalapi(session=db)

    assert result.processed == 2
    assert result.created == 2
    assert result.updated == 0
    assert result.errors == 0

    map_one = await db.get(Map, first_id)
    map_two = await db.get(Map, second_id)
    assert map_one is not None
    assert map_two is not None
    assert map_one.name == duplicate_name
    assert map_two.name == duplicate_name


def test_normalize_datetime_fallback_for_invalid_values() -> None:
    fallback = _normalize_datetime(MAP_DATETIME_FALLBACK)
    assert _normalize_datetime(None) == fallback
    assert _normalize_datetime("bad-value") == fallback
    assert _normalize_datetime("0001-01-01T00:00:00") == fallback


@pytest.mark.asyncio
async def test_sync_maps_from_globalapi_marks_missing_rows_invalid(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale_id = int(datetime.now(UTC).timestamp()) % 100000 + 940000
    upstream_id = stale_id + 1

    await db.exec(delete(Map).where(Map.id.in_([stale_id, upstream_id])))
    await db.commit()

    db.add(
        Map(
            id=stale_id,
            name=f"kz_stale_{stale_id}",
            filesize=1,
            validated=True,
            difficulty=4,
            created_on=datetime(2020, 1, 1, tzinfo=UTC),
            updated_on=datetime(2020, 1, 1, tzinfo=UTC),
            approved_by_steamid64=0,
            synced_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
    )
    await db.commit()

    async def _mock_fetch() -> list[dict[str, object]]:
        return [
            {
                "id": upstream_id,
                "name": f"kz_upstream_{upstream_id}",
                "filesize": 100,
                "validated": True,
                "difficulty": 6,
                "created_on": "2021-01-01T00:00:00",
                "updated_on": "2021-01-01T00:00:00",
                "approved_by_steamid64": "0",
                "workshop_url": None,
            }
        ]

    monkeypatch.setattr(
        "app.services.globalapi_maps_sync.fetch_maps_from_globalapi",
        _mock_fetch,
    )

    result = await sync_maps_from_globalapi(session=db)

    assert result.processed == 1
    assert result.created == 1
    assert result.updated == 1

    stale_map = await db.get(Map, stale_id)
    assert stale_map is not None
    assert stale_map.validated is False


@pytest.mark.asyncio
async def test_sync_maps_from_globalapi_bootstraps_missing_kzt_skz_main_course_tiers(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    map_id = int(datetime.now(UTC).timestamp()) % 100000 + 950000
    await db.exec(delete(Map).where(Map.id == map_id))
    await db.commit()

    db.add(
        Map(
            id=map_id,
            name=f"kz_seed_{map_id}",
            filesize=1,
            validated=False,
            difficulty=1,
            created_on=datetime(2020, 1, 1, tzinfo=UTC),
            updated_on=datetime(2020, 1, 1, tzinfo=UTC),
            approved_by_steamid64=0,
            synced_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
    )
    await db.commit()

    course = MapCourse(map_id=map_id, stage=0)
    db.add(course)
    await db.commit()
    await db.refresh(course)
    assert course.id is not None
    course_id = course.id

    async def _mock_fetch() -> list[dict[str, object]]:
        return [
            {
                "id": map_id,
                "name": f"kz_bootstrap_{map_id}",
                "filesize": 100,
                "validated": True,
                "difficulty": 7,
                "created_on": "2021-01-01T00:00:00",
                "updated_on": "2021-01-01T00:00:00",
                "approved_by_steamid64": "0",
                "workshop_url": None,
            }
        ]

    monkeypatch.setattr(
        "app.services.globalapi_maps_sync.fetch_maps_from_globalapi",
        _mock_fetch,
    )

    await sync_maps_from_globalapi(session=db)

    kzt_tier = await db.get(MapCourseTier, (course_id, KZMode.KZT))
    skz_tier = await db.get(MapCourseTier, (course_id, KZMode.SKZ))
    assert kzt_tier is not None
    assert skz_tier is not None
    assert kzt_tier.tier == 7
    assert skz_tier.tier == 7
    assert kzt_tier.updated_by_id == "globalapi-map-sync"
    assert skz_tier.updated_by_id == "globalapi-map-sync"
    assert (await db.get(MapCourseTier, (course_id, KZMode.NKZ))) is None
    assert (await db.get(MapCourseTier, (course_id, KZMode.VNL))) is None


@pytest.mark.asyncio
async def test_sync_maps_from_globalapi_updates_kzt_skz_tiers_when_difficulty_changes(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    map_id = int(datetime.now(UTC).timestamp()) % 100000 + 960000
    await db.exec(delete(Map).where(Map.id == map_id))
    await db.commit()

    db.add(
        Map(
            id=map_id,
            name=f"kz_seed_{map_id}",
            filesize=1,
            validated=False,
            difficulty=1,
            created_on=datetime(2020, 1, 1, tzinfo=UTC),
            updated_on=datetime(2020, 1, 1, tzinfo=UTC),
            approved_by_steamid64=0,
            synced_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
    )
    await db.commit()

    course = MapCourse(map_id=map_id, stage=0)
    db.add(course)
    await db.commit()
    await db.refresh(course)
    assert course.id is not None
    course_id = course.id

    db.add(
        MapCourseTier(
            course_id=course_id,
            mode=KZMode.KZT,
            tier=3,
            updated_by_id="existing",
        )
    )
    db.add(
        MapCourseTier(
            course_id=course_id,
            mode=KZMode.SKZ,
            tier=4,
            updated_by_id="existing",
        )
    )
    db.add(
        MapCourseTier(
            course_id=course_id,
            mode=KZMode.NKZ,
            tier=2,
            updated_by_id="existing",
        )
    )
    db.add(
        MapCourseTier(
            course_id=course_id,
            mode=KZMode.VNL,
            tier=5,
            updated_by_id="existing",
        )
    )
    await db.commit()

    async def _mock_fetch() -> list[dict[str, object]]:
        return [
            {
                "id": map_id,
                "name": f"kz_existing_tiers_{map_id}",
                "filesize": 100,
                "validated": True,
                "difficulty": 8,
                "created_on": "2021-01-01T00:00:00",
                "updated_on": "2021-01-01T00:00:00",
                "approved_by_steamid64": "0",
                "workshop_url": None,
            }
        ]

    monkeypatch.setattr(
        "app.services.globalapi_maps_sync.fetch_maps_from_globalapi",
        _mock_fetch,
    )

    await sync_maps_from_globalapi(session=db)

    kzt_tier = await db.get(MapCourseTier, (course_id, KZMode.KZT))
    skz_tier = await db.get(MapCourseTier, (course_id, KZMode.SKZ))
    nkz_tier = await db.get(MapCourseTier, (course_id, KZMode.NKZ))
    vnl_tier = await db.get(MapCourseTier, (course_id, KZMode.VNL))
    assert kzt_tier is not None
    assert skz_tier is not None
    assert nkz_tier is not None
    assert vnl_tier is not None
    assert kzt_tier.tier == 8
    assert skz_tier.tier == 8
    assert kzt_tier.updated_by_id == "globalapi-map-sync"
    assert skz_tier.updated_by_id == "globalapi-map-sync"
    assert nkz_tier.tier == 2
    assert nkz_tier.updated_by_id == "existing"
    assert vnl_tier.tier == 5
    assert vnl_tier.updated_by_id == "existing"


@pytest.mark.asyncio
async def test_sync_maps_from_globalapi_preserves_kzt_skz_tiers_when_difficulty_matches(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    map_id = int(datetime.now(UTC).timestamp()) % 100000 + 965000
    await db.exec(delete(Map).where(Map.id == map_id))
    await db.commit()

    db.add(
        Map(
            id=map_id,
            name=f"kz_seed_{map_id}",
            filesize=1,
            validated=False,
            difficulty=8,
            created_on=datetime(2020, 1, 1, tzinfo=UTC),
            updated_on=datetime(2020, 1, 1, tzinfo=UTC),
            approved_by_steamid64=0,
            synced_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
    )
    await db.commit()

    course = MapCourse(map_id=map_id, stage=0)
    db.add(course)
    await db.commit()
    await db.refresh(course)
    assert course.id is not None
    course_id = course.id

    db.add(
        MapCourseTier(
            course_id=course_id,
            mode=KZMode.KZT,
            tier=3,
            updated_by_id="existing",
        )
    )
    db.add(
        MapCourseTier(
            course_id=course_id,
            mode=KZMode.SKZ,
            tier=4,
            updated_by_id="existing",
        )
    )
    await db.commit()

    async def _mock_fetch() -> list[dict[str, object]]:
        return [
            {
                "id": map_id,
                "name": f"kz_existing_tiers_{map_id}",
                "filesize": 100,
                "validated": True,
                "difficulty": 8,
                "created_on": "2021-01-01T00:00:00",
                "updated_on": "2021-01-01T00:00:00",
                "approved_by_steamid64": "0",
                "workshop_url": None,
            }
        ]

    monkeypatch.setattr(
        "app.services.globalapi_maps_sync.fetch_maps_from_globalapi",
        _mock_fetch,
    )

    await sync_maps_from_globalapi(session=db)

    kzt_tier = await db.get(MapCourseTier, (course_id, KZMode.KZT))
    skz_tier = await db.get(MapCourseTier, (course_id, KZMode.SKZ))
    assert kzt_tier is not None
    assert skz_tier is not None
    assert kzt_tier.tier == 3
    assert skz_tier.tier == 4
    assert kzt_tier.updated_by_id == "existing"
    assert skz_tier.updated_by_id == "existing"


@pytest.mark.asyncio
async def test_sync_maps_from_globalapi_does_not_seed_non_main_course_tiers(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    map_id = int(datetime.now(UTC).timestamp()) % 100000 + 970000
    await db.exec(delete(Map).where(Map.id == map_id))
    await db.commit()

    db.add(
        Map(
            id=map_id,
            name=f"kz_seed_{map_id}",
            filesize=1,
            validated=False,
            difficulty=1,
            created_on=datetime(2020, 1, 1, tzinfo=UTC),
            updated_on=datetime(2020, 1, 1, tzinfo=UTC),
            approved_by_steamid64=0,
            synced_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
    )
    await db.commit()

    db.add(MapCourse(map_id=map_id, stage=1))
    await db.commit()

    async def _mock_fetch() -> list[dict[str, object]]:
        return [
            {
                "id": map_id,
                "name": f"kz_stage_only_{map_id}",
                "filesize": 100,
                "validated": True,
                "difficulty": 5,
                "created_on": "2021-01-01T00:00:00",
                "updated_on": "2021-01-01T00:00:00",
                "approved_by_steamid64": "0",
                "workshop_url": None,
            }
        ]

    monkeypatch.setattr(
        "app.services.globalapi_maps_sync.fetch_maps_from_globalapi",
        _mock_fetch,
    )

    await sync_maps_from_globalapi(session=db)

    assert (await db.exec(select(MapCourseTier))).all() == []
