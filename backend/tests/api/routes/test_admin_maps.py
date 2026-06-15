from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import (
    KZMode,
    Map,
    MapCourse,
    MapCourseTier,
    Player,
    RecordFilter,
    UserRole,
    legacy_mode_id_to_kz_mode,
)


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
    if tier is not None and course is not None and course.id is not None:
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
    return record_filter


async def _issue_role_headers(
    client: AsyncClient,
    *,
    steamid64: int,
    roles: list[UserRole],
) -> dict[str, str]:
    response = await client.post(
        f"{settings.API_V1_STR}/private/auth/session",
        json={
            "steamid64": steamid64,
            "roles": [role.value for role in roles],
            "is_active": True,
            "name": "Admin Maps Tester",
        },
    )
    payload = response.json()
    return {"Authorization": f"Bearer {payload['access_token']}"}


@pytest.mark.asyncio
async def test_admin_maps_require_map_admin_or_superuser(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    map_admin_headers = await _issue_role_headers(
        client,
        steamid64=76561199011110001,
        roles=[UserRole.MAP_ADMIN],
    )
    unauthenticated_response = await client.get(f"{settings.API_V1_STR}/admin/maps")
    normal_user_response = await client.get(
        f"{settings.API_V1_STR}/admin/maps",
        headers=normal_user_token_headers,
    )
    map_admin_response = await client.get(
        f"{settings.API_V1_STR}/admin/maps",
        headers=map_admin_headers,
    )

    assert unauthenticated_response.status_code in {401, 403}
    assert normal_user_response.status_code == 403
    assert map_admin_response.status_code == 200


@pytest.mark.asyncio
async def test_map_admin_can_update_map_validation_and_course_tier(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    map_admin_headers = await _issue_role_headers(
        client,
        steamid64=76561199011110002,
        roles=[UserRole.MAP_ADMIN],
    )
    map_obj = await _create_map(db, id=991005, name="kz_map_admin_access")
    await _create_record_filter(
        db,
        id=99100501,
        map_id=map_obj.id,
        stage=0,
        mode_id=200,
        tier=2,
    )
    course = (
        await db.exec(
            select(MapCourse).where(
                MapCourse.map_id == map_obj.id,
                MapCourse.stage == 0,
            )
        )
    ).first()
    assert course is not None
    assert course.id is not None

    map_response = await client.patch(
        f"{settings.API_V1_STR}/admin/maps/{map_obj.id}",
        headers=map_admin_headers,
        json={"validated": False},
    )
    course_tier_response = await client.patch(
        f"{settings.API_V1_STR}/admin/course-tiers/{course.id}/{KZMode.KZT.value}",
        headers=map_admin_headers,
        json={"tier": 6},
    )

    assert map_response.status_code == 200
    assert map_response.json()["validated"] is False
    assert course_tier_response.status_code == 200
    assert course_tier_response.json()["tier"] == 6
    assert course_tier_response.json()["updated_by_id"] == "76561199011110002"


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
    assert payload["data"][0]["authors"] == ["76561198000000001"]
    assert payload["data"][0]["no_steamid_names"] == ["Unknown Mapper"]
    assert payload["data"][0]["tiers"]["OVR"] == 0


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
    assert refreshed.authors == ["76561198000000001"]
    assert refreshed.no_steamid_names == ["Unknown Mapper"]


@pytest.mark.asyncio
async def test_update_admin_map_updates_author_fields(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    map_obj = await _create_map(
        db,
        id=991011,
        name="kz_admin_author_update",
        validated=True,
    )

    response = await client.patch(
        f"{settings.API_V1_STR}/admin/maps/{map_obj.id}",
        headers=superuser_token_headers,
        json={
            "validated": True,
            "authors": [
                " 76561198000000002 ",
                "Name In Wrong Field",
                "76561198000000002",
            ],
            "no_steamid_names": ["Manual Name", "76561198000000003"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["authors"] == ["76561198000000002"]
    assert payload["no_steamid_names"] == ["Manual Name", "Name In Wrong Field"]

    refreshed = await db.get(Map, map_obj.id)
    assert refreshed is not None
    assert refreshed.authors == ["76561198000000002"]
    assert refreshed.no_steamid_names == ["Manual Name", "Name In Wrong Field"]
    author_player = await db.get(Player, 76561198000000002)
    assert author_player is not None
    assert author_player.name == "76561198000000002"


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
async def test_read_admin_map_course_tiers_returns_grouped_stage_rows(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    map_obj = await _create_map(db, id=991025, name="kz_admin_course_tiers")
    await _create_record_filter(
        db,
        id=99102501,
        map_id=map_obj.id,
        stage=0,
        mode_id=200,
        tier=3,
    )
    await _create_record_filter(
        db,
        id=99102502,
        map_id=map_obj.id,
        stage=1,
        mode_id=201,
        tier=4,
    )

    response = await client.get(
        f"{settings.API_V1_STR}/admin/maps/{map_obj.id}/course-tiers",
        headers=superuser_token_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["map_id"] == map_obj.id
    assert payload["stages"][0]["stage"] == 0
    assert payload["stages"][0]["course_tiers"][0]["mode"] == "KZT"
    assert payload["stages"][0]["course_tiers"][0]["tier"] == 3
    assert payload["stages"][0]["course_tiers"][2]["mode"] == "VNL"
    assert payload["stages"][0]["course_tiers"][2]["tier"] == 0
    assert payload["stages"][1]["stage"] == 1
    assert payload["stages"][1]["course_tiers"][1]["mode"] == "SKZ"
    assert payload["stages"][1]["course_tiers"][1]["tier"] == 4


@pytest.mark.asyncio
async def test_update_admin_course_tier(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    map_obj = await _create_map(db, id=991030, name="kz_admin_tier_update")
    await _create_record_filter(
        db,
        id=99103001,
        map_id=map_obj.id,
        stage=0,
        mode_id=200,
        tier=3,
    )
    course = (
        await db.exec(
            select(MapCourse).where(
                MapCourse.map_id == map_obj.id,
                MapCourse.stage == 0,
            )
        )
    ).first()
    assert course is not None
    assert course.id is not None

    response = await client.patch(
        f"{settings.API_V1_STR}/admin/course-tiers/{course.id}/{KZMode.KZT.value}",
        headers=superuser_token_headers,
        json={"tier": 6},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tier"] == 6
    assert payload["updated_by_id"] == str(settings.SUPER_USER_STEAMID64)

    refreshed = await db.get(MapCourseTier, (course.id, KZMode.KZT))
    assert refreshed is not None
    assert refreshed.tier == 6
    assert refreshed.updated_by_id == str(settings.SUPER_USER_STEAMID64)


@pytest.mark.asyncio
async def test_update_admin_course_tier_rejects_invalid_tier_and_missing_course(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
) -> None:
    missing_course_response = await client.patch(
        f"{settings.API_V1_STR}/admin/course-tiers/999999/{KZMode.KZT.value}",
        headers=superuser_token_headers,
        json={"tier": 4},
    )
    invalid_tier_response = await client.patch(
        f"{settings.API_V1_STR}/admin/course-tiers/999999/{KZMode.KZT.value}",
        headers=superuser_token_headers,
        json={"tier": 9},
    )

    assert missing_course_response.status_code == 404
    assert invalid_tier_response.status_code == 422


@pytest.mark.asyncio
async def test_admin_map_and_course_tier_not_found(
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
    course_tiers_response = await client.get(
        f"{settings.API_V1_STR}/admin/maps/999999999/course-tiers",
        headers=superuser_token_headers,
    )
    course_tier_response = await client.patch(
        f"{settings.API_V1_STR}/admin/course-tiers/999999999/{KZMode.KZT.value}",
        headers=superuser_token_headers,
        json={"tier": 1},
    )

    assert map_response.status_code == 404
    assert filters_response.status_code == 404
    assert course_tiers_response.status_code == 404
    assert course_tier_response.status_code == 404
