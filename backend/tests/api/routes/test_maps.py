from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlmodel import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import Map, MapSyncResult, RecordFilter
from app.services.globalapi_maps_sync import GlobalAPIMapsSyncError


async def _create_map(db: AsyncSession, *, id: int = 930200) -> Map:
    await db.exec(delete(Map).where(Map.id == id))
    await db.commit()

    map_obj = Map(
        id=id,
        name=f"kz_test_{id}",
        filesize=123456,
        validated=True,
        difficulty=5,
        created_on=datetime(2021, 1, 1, tzinfo=UTC),
        updated_on=datetime(2021, 1, 2, tzinfo=UTC),
        approved_by_steamid64=76561198003275951,
        workshop_id=1986459033,
        authors=["76561198000000001"],
        no_steamid_names=["Unknown Mapper"],
        synced_at=datetime(2021, 1, 3, tzinfo=UTC),
    )
    db.add(map_obj)
    await db.commit()
    await db.refresh(map_obj)
    return map_obj


async def _create_record_filter(
    db: AsyncSession,
    *,
    id: int,
    map_id: int,
    stage: int,
    mode_id: int,
    tier: int | None,
    tickrate: int = 128,
    has_teleports: bool = False,
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
        updated_by_id="0",
    )
    db.add(record_filter)
    await db.commit()
    await db.refresh(record_filter)
    return record_filter


@pytest.mark.asyncio
async def test_read_maps_v0_contract(client: AsyncClient, db: AsyncSession) -> None:
    await _create_map(db, id=930200)

    response = await client.get("/v0/maps", params={"id": 930200, "limit": 10000})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) >= 1

    map_payload = next(item for item in payload if item["id"] == 930200)
    assert map_payload["name"] == "kz_test_930200"
    assert map_payload["difficulty"] == 5
    assert map_payload["approved_by_steamid64"] == "76561198003275951"
    assert map_payload["workshop_url"] == (
        "https://steamcommunity.com/sharedfiles/filedetails/?id=1986459033"
    )
    assert map_payload["download_url"] == ""


@pytest.mark.asyncio
async def test_read_map_v1_by_id(client: AsyncClient, db: AsyncSession) -> None:
    await _create_map(db, id=930201)

    response = await client.get(f"{settings.API_V1_STR}/maps/930201")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == 930201
    assert payload["approved_by_steamid64"] == "76561198003275951"
    assert payload["workshop_id"] == 1986459033
    assert payload["authors"] == ["76561198000000001"]
    assert payload["no_steamid_names"] == ["Unknown Mapper"]
    assert payload["tiers"] == {"OVR": 5, "KZT": 5, "SKZ": 5, "VNL": 5}
    assert payload["workshop_url"] == (
        "https://steamcommunity.com/sharedfiles/filedetails/?id=1986459033"
    )


@pytest.mark.asyncio
async def test_read_map_v1_returns_scope_aware_main_course_tiers(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await _create_map(db, id=930202)
    await _create_record_filter(
        db,
        id=930260,
        map_id=930202,
        stage=0,
        mode_id=200,
        tier=6,
    )
    await _create_record_filter(
        db,
        id=930261,
        map_id=930202,
        stage=0,
        mode_id=201,
        tier=3,
    )
    await _create_record_filter(
        db,
        id=930262,
        map_id=930202,
        stage=0,
        mode_id=202,
        tier=8,
    )

    by_id_response = await client.get(f"{settings.API_V1_STR}/maps/930202")
    by_name_response = await client.get(f"{settings.API_V1_STR}/maps/name/kz_test_930202")
    filtered_response = await client.get(
        f"{settings.API_V1_STR}/maps",
        params={"id": 930202},
    )

    assert by_id_response.status_code == 200
    assert by_id_response.json()["tiers"] == {
        "OVR": 3,
        "KZT": 6,
        "SKZ": 3,
        "VNL": 8,
    }
    assert by_name_response.status_code == 200
    assert by_name_response.json()["tiers"] == {
        "OVR": 3,
        "KZT": 6,
        "SKZ": 3,
        "VNL": 8,
    }
    assert filtered_response.status_code == 200
    assert filtered_response.json()[0]["tiers"] == {
        "OVR": 3,
        "KZT": 6,
        "SKZ": 3,
        "VNL": 8,
    }


@pytest.mark.asyncio
async def test_read_map_v0_not_found(client: AsyncClient) -> None:
    response = await client.get("/v0/maps/999999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Map not found"}


@pytest.mark.asyncio
async def test_sync_maps_v1_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(f"{settings.API_V1_STR}/maps/sync")
    assert response.status_code in {401, 403}


@pytest.mark.asyncio
async def test_sync_maps_v1_superuser(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mocked_sync = AsyncMock(
        return_value=MapSyncResult(processed=10, created=2, updated=8, errors=0)
    )
    monkeypatch.setattr("app.api.v1.maps.sync_maps_from_globalapi", mocked_sync)

    response = await client.post(
        f"{settings.API_V1_STR}/maps/sync",
        headers=superuser_token_headers,
    )

    assert response.status_code == 200
    assert response.json() == {
        "processed": 10,
        "created": 2,
        "updated": 8,
        "errors": 0,
    }


@pytest.mark.asyncio
async def test_sync_maps_v1_returns_502_for_upstream_error(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mocked_sync = AsyncMock(
        side_effect=GlobalAPIMapsSyncError("Failed to fetch maps from GlobalAPI")
    )
    monkeypatch.setattr("app.api.v1.maps.sync_maps_from_globalapi", mocked_sync)

    response = await client.post(
        f"{settings.API_V1_STR}/maps/sync",
        headers=superuser_token_headers,
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Failed to fetch maps from GlobalAPI"}
