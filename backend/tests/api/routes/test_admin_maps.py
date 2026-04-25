from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlmodel import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import Map, RecordFilter


async def _create_map(
    db: AsyncSession,
    *,
    id: int,
    name: str,
    validated: bool = True,
) -> Map:
    await db.exec(delete(RecordFilter).where(RecordFilter.map_id == id))
    await db.exec(delete(Map).where(Map.id == id))
    await db.commit()

    map_obj = Map(
        id=id,
        name=name,
        filesize=123456,
        validated=validated,
        difficulty=5,
        created_on=datetime(2021, 1, 1, tzinfo=UTC),
        updated_on=datetime(2021, 1, 2, tzinfo=UTC),
        approved_by_steamid64=76561198003275951 if validated else 0,
        workshop_id=1986459033,
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
async def test_admin_maps_require_superuser(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    unauthenticated_response = await client.get(f"{settings.API_V1_STR}/admin/maps")
    normal_user_response = await client.get(
        f"{settings.API_V1_STR}/admin/maps",
        headers=normal_user_token_headers,
    )

    assert unauthenticated_response.status_code in {401, 403}
    assert normal_user_response.status_code == 403


@pytest.mark.asyncio
async def test_read_admin_maps_filters_searches_and_paginates(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    await _create_map(db, id=991001, name="kz_admin_alpha", validated=True)
    await _create_map(db, id=991002, name="kz_admin_beta", validated=False)
    await _create_map(db, id=991003, name="kz_other", validated=True)

    response = await client.get(
        f"{settings.API_V1_STR}/admin/maps",
        headers=superuser_token_headers,
        params={"q": "admin", "validated": "true", "offset": 0, "limit": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert [row["name"] for row in payload["data"]] == ["kz_admin_alpha"]
    assert payload["data"][0]["approved_by_steamid64"] == "76561198003275951"
    assert payload["data"][0]["tiers"]["OVR"] == 5


@pytest.mark.asyncio
async def test_update_admin_map_toggles_validation_metadata(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    map_obj = await _create_map(
        db,
        id=991010,
        name="kz_admin_validation",
        validated=True,
    )

    unvalidate_response = await client.patch(
        f"{settings.API_V1_STR}/admin/maps/{map_obj.id}",
        headers=superuser_token_headers,
        json={"validated": False},
    )
    assert unvalidate_response.status_code == 200
    assert unvalidate_response.json()["validated"] is False
    assert unvalidate_response.json()["approved_by_steamid64"] == "0"

    validate_response = await client.patch(
        f"{settings.API_V1_STR}/admin/maps/{map_obj.id}",
        headers=superuser_token_headers,
        json={"validated": True},
    )
    assert validate_response.status_code == 200
    assert validate_response.json()["validated"] is True
    assert validate_response.json()["approved_by_steamid64"] == str(
        settings.SUPER_USER_STEAMID64
    )

    refreshed = await db.get(Map, map_obj.id)
    assert refreshed is not None
    assert refreshed.validated is True
    assert refreshed.approved_by_steamid64 == settings.SUPER_USER_STEAMID64
    assert refreshed.updated_at > datetime(2021, 1, 2, tzinfo=UTC)


@pytest.mark.asyncio
async def test_read_admin_map_record_filters_returns_128_tick_grouped_by_stage(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    map_obj = await _create_map(db, id=991020, name="kz_admin_filters")
    await _create_record_filter(
        db,
        id=99102001,
        map_id=map_obj.id,
        stage=1,
        mode_id=201,
        tier=4,
        has_teleports=True,
    )
    await _create_record_filter(
        db,
        id=99102002,
        map_id=map_obj.id,
        stage=0,
        mode_id=200,
        tier=3,
    )
    await _create_record_filter(
        db,
        id=99102003,
        map_id=map_obj.id,
        stage=0,
        mode_id=202,
        tier=5,
        tickrate=64,
    )
    await _create_record_filter(
        db,
        id=99102004,
        map_id=-1,
        stage=0,
        mode_id=200,
        tier=2,
    )

    response = await client.get(
        f"{settings.API_V1_STR}/admin/maps/{map_obj.id}/record-filters",
        headers=superuser_token_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "map_id": map_obj.id,
        "stages": [
            {
                "stage": 0,
                "record_filters": [
                    {
                        "id": 99102002,
                        "map_id": map_obj.id,
                        "stage": 0,
                        "mode": "KZT",
                        "has_teleports": False,
                        "tier": 3,
                        "created_on": payload["stages"][0]["record_filters"][0][
                            "created_on"
                        ],
                        "updated_on": payload["stages"][0]["record_filters"][0][
                            "updated_on"
                        ],
                        "updated_by_id": "0",
                    },
                ],
            },
            {
                "stage": 1,
                "record_filters": [
                    {
                        "id": 99102001,
                        "map_id": map_obj.id,
                        "stage": 1,
                        "mode": "SKZ",
                        "has_teleports": True,
                        "tier": 4,
                        "created_on": payload["stages"][1]["record_filters"][0][
                            "created_on"
                        ],
                        "updated_on": payload["stages"][1]["record_filters"][0][
                            "updated_on"
                        ],
                        "updated_by_id": "0",
                    },
                ],
            },
        ],
    }


@pytest.mark.asyncio
async def test_update_admin_record_filter_tier(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    map_obj = await _create_map(db, id=991030, name="kz_admin_tier_update")
    record_filter = await _create_record_filter(
        db,
        id=99103001,
        map_id=map_obj.id,
        stage=0,
        mode_id=200,
        tier=3,
    )

    response = await client.patch(
        f"{settings.API_V1_STR}/admin/record-filters/{record_filter.id}",
        headers=superuser_token_headers,
        json={"tier": None},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tier"] is None
    assert payload["updated_by_id"] == str(settings.SUPER_USER_STEAMID64)

    refreshed = await db.get(RecordFilter, record_filter.id)
    assert refreshed is not None
    assert refreshed.tier is None
    assert refreshed.updated_by_id == str(settings.SUPER_USER_STEAMID64)


@pytest.mark.asyncio
async def test_update_admin_record_filter_rejects_wildcard_and_non_128_tick(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    map_obj = await _create_map(db, id=991040, name="kz_admin_rejected_filters")
    wildcard = await _create_record_filter(
        db,
        id=99104001,
        map_id=-1,
        stage=0,
        mode_id=200,
        tier=2,
    )
    non_128_tick = await _create_record_filter(
        db,
        id=99104002,
        map_id=map_obj.id,
        stage=0,
        mode_id=200,
        tier=2,
        tickrate=64,
    )

    wildcard_response = await client.patch(
        f"{settings.API_V1_STR}/admin/record-filters/{wildcard.id}",
        headers=superuser_token_headers,
        json={"tier": 4},
    )
    non_128_response = await client.patch(
        f"{settings.API_V1_STR}/admin/record-filters/{non_128_tick.id}",
        headers=superuser_token_headers,
        json={"tier": 4},
    )
    invalid_tier_response = await client.patch(
        f"{settings.API_V1_STR}/admin/record-filters/{non_128_tick.id}",
        headers=superuser_token_headers,
        json={"tier": 9},
    )

    assert wildcard_response.status_code == 422
    assert non_128_response.status_code == 422
    assert invalid_tier_response.status_code == 422


@pytest.mark.asyncio
async def test_admin_map_and_record_filter_not_found(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
) -> None:
    map_response = await client.patch(
        f"{settings.API_V1_STR}/admin/maps/999999999",
        headers=superuser_token_headers,
        json={"validated": True},
    )
    filters_response = await client.get(
        f"{settings.API_V1_STR}/admin/maps/999999999/record-filters",
        headers=superuser_token_headers,
    )
    filter_response = await client.patch(
        f"{settings.API_V1_STR}/admin/record-filters/999999999",
        headers=superuser_token_headers,
        json={"tier": 1},
    )

    assert map_response.status_code == 404
    assert filters_response.status_code == 404
    assert filter_response.status_code == 404
