from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlmodel import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import Map, MapSyncResult
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
    assert payload["workshop_url"] == (
        "https://steamcommunity.com/sharedfiles/filedetails/?id=1986459033"
    )


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
