from datetime import UTC, datetime

import pytest
from sqlmodel import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Map
from app.services.globalapi_maps_sync import (
    MAP_DATETIME_FALLBACK,
    _normalize_datetime,
    sync_maps_from_globalapi,
)


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
    assert refreshed_200.created_on == _normalize_datetime("0001-01-01T00:00:00")
    assert refreshed_200.workshop_id == 1986459033

    refreshed_201 = await db.get(Map, created_id)
    assert refreshed_201 is not None
    assert refreshed_201.created_on == _normalize_datetime(MAP_DATETIME_FALLBACK)
    assert refreshed_201.updated_on == _normalize_datetime(MAP_DATETIME_FALLBACK)


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
