import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.models import (
    Map,
    MapCourse,
    Player,
    MapReview,
    MapReviewSummaryCache,
    MapSyncResult,
    RecordFilter,
    ServerGlobalapi,
)
from app.models.utils import get_datetime_utc
from app.services.globalapi_maps_sync import GlobalAPIMapsSyncError
from tests.utils.server import create_server_group
from tests.utils.utils import random_steamid64


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


async def _auth_user(
    client: AsyncClient,
    *,
    steamid64: int,
    name: str,
) -> dict[str, str]:
    response = await client.post(
        f"{settings.API_V1_STR}/private/auth/session",
        json={
            "steamid64": steamid64,
            "is_superuser": False,
            "is_active": True,
            "name": name,
        },
    )
    payload = response.json()
    return {"Authorization": f"Bearer {payload['access_token']}"}


async def _create_review(
    db: AsyncSession,
    *,
    steamid64: int,
    map_id: int,
    updated_at: datetime,
    overall: int,
    server_group_id: uuid.UUID | None = None,
    comment_text: str | None = None,
) -> MapReview:
    comment = None
    if comment_text is not None:
        comment = {
            "text": comment_text,
            "language": "en",
            "created_at": updated_at.isoformat(),
            "updated_at": updated_at.isoformat(),
        }

    review = MapReview(
        steamid64=steamid64,
        map_id=map_id,
        server_group_id=server_group_id,
        content={
            "overall": overall,
            "gameplay": None,
            "visuals": None,
            "comment": comment,
        },
        created_at=updated_at,
        updated_at=updated_at,
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)
    return review


async def _create_ovr_pb(
    db: AsyncSession,
    *,
    steamid64: int,
    map_id: int,
    stage: int = 0,
    server_id: int | None = None,
) -> None:
    course = (
        await db.exec(
            select(MapCourse).where(MapCourse.map_id == map_id, MapCourse.stage == stage)
        )
    ).first()
    if course is None:
        course = MapCourse(map_id=map_id, stage=stage)
        db.add(course)
        await db.commit()
        await db.refresh(course)

    resolved_server_id = server_id or map_id + 1_000_000
    if await db.get(ServerGlobalapi, resolved_server_id) is None:
        db.add(
            ServerGlobalapi(
                id=resolved_server_id,
                port=27015,
                ip=f"203.0.113.{map_id % 200 + 1}",
                name=f"Test Server {map_id}",
                owner_steamid64=0,
                approval_status=1,
                approved_by_steamid64=0,
            )
        )
        await db.commit()

    await crud.upsert_record(
        session=db,
        record_id=map_id + 2_000_000,
        record_uuid=None,
        steamid64=steamid64,
        server_id=resolved_server_id,
        mode_id=200,
        map_id=map_id,
        stage=stage,
        time_seconds=Decimal("12.345"),
        teleports=1,
        points=0,
        created_on=datetime(2099, 1, 1, tzinfo=UTC),
        updated_on=datetime(2099, 1, 1, tzinfo=UTC),
        updated_by=steamid64,
        replay_id=None,
        is_valid=True,
    )


async def _create_player(db: AsyncSession, *, steamid64: int, name: str) -> None:
    db.add(Player(steamid64=steamid64, name=name))
    await db.commit()


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


@pytest.mark.asyncio
async def test_read_map_wrs_v1_returns_nub_and_pro_rows(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    map_obj = await _create_map(db, id=930211)
    server_id = 930311
    db.add(
        ServerGlobalapi(
            id=server_id,
            port=27015,
            ip="203.0.113.88",
            name="WR Server",
            owner_steamid64=0,
            approval_status=1,
            approved_by_steamid64=0,
        )
    )
    await db.commit()

    nub_player = random_steamid64()
    pro_player = random_steamid64()
    await _create_player(db, steamid64=nub_player, name="Nub Winner")
    await _create_player(db, steamid64=pro_player, name="Pro Winner")

    await crud.upsert_record(
        session=db,
        record_id=9_302_110,
        record_uuid=None,
        steamid64=nub_player,
        server_id=server_id,
        mode_id=200,
        map_id=map_obj.id,
        stage=0,
        time_seconds=Decimal("10.500"),
        teleports=1,
        points=0,
        created_on=datetime(2099, 1, 1, tzinfo=UTC),
        updated_on=datetime(2099, 1, 1, tzinfo=UTC),
        updated_by=nub_player,
        replay_id=None,
        is_valid=True,
    )
    await crud.upsert_record(
        session=db,
        record_id=9_302_111,
        record_uuid=None,
        steamid64=pro_player,
        server_id=server_id,
        mode_id=201,
        map_id=map_obj.id,
        stage=0,
        time_seconds=Decimal("11.000"),
        teleports=0,
        points=0,
        created_on=datetime(2099, 1, 1, tzinfo=UTC),
        updated_on=datetime(2099, 1, 1, tzinfo=UTC),
        updated_by=pro_player,
        replay_id=None,
        is_valid=True,
    )
    await db.commit()

    response = await client.get(
        f"{settings.API_V1_STR}/maps/wrs",
        params={"map_id": map_obj.id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert [row["type"] for row in payload] == ["NUB", "PRO"]
    assert payload[0]["player"]["display_name"] == "Nub Winner"
    assert payload[0]["time"] == pytest.approx(10.5)
    assert payload[0]["map_id"] == map_obj.id
    assert payload[0]["scope"] == "OVR"
    assert payload[1]["player"]["display_name"] == "Pro Winner"
    assert payload[1]["mode_id"] == 201


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


@pytest.mark.asyncio
async def test_put_map_review_with_user_auth_upserts_website_review(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    map_obj = await _create_map(db, id=930203)
    steamid64 = random_steamid64()
    headers = await _auth_user(client, steamid64=steamid64, name="Website Reviewer")
    await _create_ovr_pb(db, steamid64=steamid64, map_id=map_obj.id)

    first_response = await client.put(
        f"{settings.API_V1_STR}/maps/reviews",
        headers=headers,
        json={
            "map_id": map_obj.id,
            "content": {
                "overall": 4,
                "gameplay": 5,
                "visuals": 3,
                "comment": {
                    "text": "The mechanics are incredible, but the textures feel dated."
                },
            },
        },
    )

    assert first_response.status_code == 200
    first_payload = first_response.json()
    assert first_payload["steamid64"] == str(steamid64)
    assert first_payload["map_id"] == map_obj.id
    assert first_payload["server_group_id"] is None
    assert first_payload["content"]["overall"] == 4
    assert first_payload["content"]["gameplay"] == 5
    assert first_payload["content"]["visuals"] == 3
    assert first_payload["content"]["comment"]["language"] == "en"
    first_review_created_at = first_payload["created_at"]
    first_comment_created_at = first_payload["content"]["comment"]["created_at"]
    first_comment_updated_at = first_payload["content"]["comment"]["updated_at"]

    second_response = await client.put(
        f"{settings.API_V1_STR}/maps/reviews",
        headers=headers,
        json={
            "map_id": map_obj.id,
            "content": {
                "overall": 5,
                "gameplay": 5,
                "visuals": 4,
                "comment": {
                    "text": "The mechanics are incredible, but the textures feel dated."
                },
            },
        },
    )

    assert second_response.status_code == 200
    second_payload = second_response.json()
    assert second_payload["created_at"] == first_review_created_at
    assert second_payload["content"]["comment"]["created_at"] == first_comment_created_at
    assert second_payload["content"]["comment"]["updated_at"] == first_comment_updated_at

    stored_review = await crud.get_map_review_by_context(
        session=db,
        steamid64=steamid64,
        map_id=map_obj.id,
        server_group_id=None,
    )
    assert stored_review is not None
    assert stored_review.content["overall"] == 5
    cached_summary = await db.get(MapReviewSummaryCache, map_obj.id)
    assert cached_summary is not None
    assert cached_summary.overall_avg == pytest.approx(5.0)
    assert cached_summary.gameplay_avg == pytest.approx(5.0)
    assert cached_summary.visuals_avg == pytest.approx(4.0)
    assert cached_summary.reviews_count == 1
    assert cached_summary.comments_count == 1


@pytest.mark.asyncio
async def test_put_map_review_with_server_group_key_can_upsert_for_any_player(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    map_obj = await _create_map(db, id=930204)
    player_steamid64 = random_steamid64()
    await _auth_user(client, steamid64=player_steamid64, name="Server Group Player")
    await _create_ovr_pb(db, steamid64=player_steamid64, map_id=map_obj.id)
    group, api_key = await create_server_group(db)

    response = await client.put(
        f"{settings.API_V1_STR}/maps/reviews",
        headers={"X-Server-Group-Key": api_key},
        json={
            "steamid64": str(player_steamid64),
            "map_id": map_obj.id,
            "content": {
                "overall": 2,
                "comment": {"text": "Nicht schlecht."},
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["steamid64"] == str(player_steamid64)
    assert payload["server_group_id"] == str(group.id)
    assert payload["content"]["comment"]["language"] == "de"


@pytest.mark.asyncio
async def test_put_map_review_requires_steamid64_for_server_group_key(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    map_obj = await _create_map(db, id=930205)
    _, api_key = await create_server_group(db)

    response = await client.put(
        f"{settings.API_V1_STR}/maps/reviews",
        headers={"X-Server-Group-Key": api_key},
        json={
            "map_id": map_obj.id,
            "content": {
                "overall": 3,
            },
        },
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "steamid64 is required"}


@pytest.mark.asyncio
async def test_put_map_review_rejects_comment_longer_than_1000_chars(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    map_obj = await _create_map(db, id=930206)
    steamid64 = random_steamid64()
    headers = await _auth_user(
        client,
        steamid64=steamid64,
        name="Length Check",
    )
    await _create_ovr_pb(db, steamid64=steamid64, map_id=map_obj.id)

    response = await client.put(
        f"{settings.API_V1_STR}/maps/reviews",
        headers=headers,
        json={
            "map_id": map_obj.id,
            "content": {
                "overall": 4,
                "comment": {"text": "x" * 1001},
            },
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_put_map_review_rejects_user_without_ovr_pb(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    map_obj = await _create_map(db, id=930210)
    steamid64 = random_steamid64()
    headers = await _auth_user(client, steamid64=steamid64, name="No PB Reviewer")

    response = await client.put(
        f"{settings.API_V1_STR}/maps/reviews",
        headers=headers,
        json={
            "map_id": map_obj.id,
            "content": {
                "overall": 4,
            },
        },
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Player must have an OVR PB on the map before submitting a review"
    }


@pytest.mark.asyncio
async def test_put_map_review_rejects_server_group_player_without_ovr_pb(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    map_obj = await _create_map(db, id=930211)
    player_steamid64 = random_steamid64()
    await _auth_user(client, steamid64=player_steamid64, name="Server Group No PB")
    _, api_key = await create_server_group(db)

    response = await client.put(
        f"{settings.API_V1_STR}/maps/reviews",
        headers={"X-Server-Group-Key": api_key},
        json={
            "steamid64": str(player_steamid64),
            "map_id": map_obj.id,
            "content": {
                "overall": 2,
            },
        },
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Player must have an OVR PB on the map before submitting a review"
    }


@pytest.mark.asyncio
async def test_read_map_reviews_returns_latest_review_per_player_per_map(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    map_one = await _create_map(db, id=930207)
    map_two = await _create_map(db, id=930208)
    player_one = random_steamid64()
    player_two = random_steamid64()
    await _auth_user(client, steamid64=player_one, name="Player One")
    await _auth_user(client, steamid64=player_two, name="Player Two")
    group, _ = await create_server_group(db)
    base_time = get_datetime_utc()

    await _create_review(
        db,
        steamid64=player_one,
        map_id=map_one.id,
        updated_at=base_time,
        overall=2,
        comment_text="older website review",
    )
    await _create_review(
        db,
        steamid64=player_one,
        map_id=map_one.id,
        updated_at=base_time + timedelta(minutes=2),
        overall=5,
        server_group_id=group.id,
        comment_text="newer server group review",
    )
    await _create_review(
        db,
        steamid64=player_one,
        map_id=map_two.id,
        updated_at=base_time + timedelta(minutes=1),
        overall=4,
        comment_text="map two review",
    )
    await _create_review(
        db,
        steamid64=player_two,
        map_id=map_one.id,
        updated_at=base_time + timedelta(minutes=3),
        overall=3,
        comment_text="player two review",
    )

    map_response = await client.get(
        f"{settings.API_V1_STR}/maps/reviews",
        params={"map_id": map_one.id},
    )

    assert map_response.status_code == 200
    map_payload = map_response.json()
    assert map_payload["count"] == 2
    assert [item["steamid64"] for item in map_payload["data"]] == [
        str(player_two),
        str(player_one),
    ]
    assert map_payload["data"][1]["content"]["overall"] == 5
    assert map_payload["data"][1]["server_group_id"] == str(group.id)

    player_response = await client.get(
        f"{settings.API_V1_STR}/maps/reviews",
        params={"steamid64": str(player_one)},
    )

    assert player_response.status_code == 200
    player_payload = player_response.json()
    assert player_payload["count"] == 2
    assert {item["map_id"] for item in player_payload["data"]} == {
        map_one.id,
        map_two.id,
    }

    exact_response = await client.get(
        f"{settings.API_V1_STR}/maps/reviews",
        params={"steamid64": str(player_one), "map_name": map_one.name},
    )

    assert exact_response.status_code == 200
    exact_payload = exact_response.json()
    assert exact_payload["count"] == 1
    assert exact_payload["data"][0]["content"]["comment"]["text"] == (
        "newer server group review"
    )


@pytest.mark.asyncio
async def test_read_map_reviews_supports_comment_and_language_filters(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    map_obj = await _create_map(db, id=930209)
    player_en = random_steamid64()
    player_ru = random_steamid64()
    player_plain = random_steamid64()
    await _auth_user(client, steamid64=player_en, name="English Reviewer")
    await _auth_user(client, steamid64=player_ru, name="Russian Reviewer")
    await _auth_user(client, steamid64=player_plain, name="Plain Reviewer")
    base_time = get_datetime_utc()

    await _create_review(
        db,
        steamid64=player_en,
        map_id=map_obj.id,
        updated_at=base_time + timedelta(minutes=1),
        overall=4,
        comment_text="great movement map",
    )
    await _create_review(
        db,
        steamid64=player_ru,
        map_id=map_obj.id,
        updated_at=base_time + timedelta(minutes=2),
        overall=5,
        comment_text="очень хорошая карта",
    )
    await _create_review(
        db,
        steamid64=player_plain,
        map_id=map_obj.id,
        updated_at=base_time + timedelta(minutes=3),
        overall=3,
        comment_text=None,
    )

    comments_only_response = await client.get(
        f"{settings.API_V1_STR}/maps/reviews",
        params={"map_id": map_obj.id, "with_comments_only": "true"},
    )

    assert comments_only_response.status_code == 200
    comments_only_payload = comments_only_response.json()
    assert comments_only_payload["count"] == 2
    assert [item["steamid64"] for item in comments_only_payload["data"]] == [
        str(player_ru),
        str(player_en),
    ]

    english_response = await client.get(
        f"{settings.API_V1_STR}/maps/reviews",
        params={"map_id": map_obj.id, "language": "en"},
    )

    assert english_response.status_code == 200
    english_payload = english_response.json()
    assert english_payload["count"] == 1
    assert english_payload["data"][0]["steamid64"] == str(player_en)
    assert english_payload["data"][0]["content"]["comment"]["language"] == "en"


@pytest.mark.asyncio
async def test_rebuild_map_review_summary_counts_latest_reviews_only(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    map_obj = await _create_map(db, id=930212)
    player_one = random_steamid64()
    player_two = random_steamid64()
    await _auth_user(client, steamid64=player_one, name="Summary One")
    await _auth_user(client, steamid64=player_two, name="Summary Two")
    base_time = get_datetime_utc()
    group, _ = await create_server_group(db)

    await _create_review(
        db,
        steamid64=player_one,
        map_id=map_obj.id,
        updated_at=base_time,
        overall=2,
        comment_text="older review",
    )
    await _create_review(
        db,
        steamid64=player_one,
        map_id=map_obj.id,
        updated_at=base_time + timedelta(minutes=1),
        overall=4,
        server_group_id=group.id,
        comment_text=None,
    )
    await _create_review(
        db,
        steamid64=player_two,
        map_id=map_obj.id,
        updated_at=base_time + timedelta(minutes=2),
        overall=5,
        comment_text="latest with comment",
    )

    summary = await crud.rebuild_map_review_summary(session=db, map_id=map_obj.id)

    assert summary is not None
    assert summary.reviews_count == 2
    assert summary.overall_avg == pytest.approx(4.5)
    assert summary.gameplay_avg is None
    assert summary.visuals_avg is None
    assert summary.gameplay_count == 0
    assert summary.visuals_count == 0
    assert summary.comments_count == 1

    cached = await db.get(MapReviewSummaryCache, map_obj.id)
    assert cached is not None
    assert cached.reviews_count == 2


@pytest.mark.asyncio
async def test_read_map_v1_includes_review_summary(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    map_obj = await _create_map(db, id=930213)
    player_one = random_steamid64()
    player_two = random_steamid64()
    await _auth_user(client, steamid64=player_one, name="Map Summary One")
    await _auth_user(client, steamid64=player_two, name="Map Summary Two")
    await _create_review(
        db,
        steamid64=player_one,
        map_id=map_obj.id,
        updated_at=get_datetime_utc(),
        overall=4,
        comment_text="Solid map",
    )
    await _create_review(
        db,
        steamid64=player_two,
        map_id=map_obj.id,
        updated_at=get_datetime_utc() + timedelta(minutes=1),
        overall=5,
        comment_text=None,
    )
    await crud.rebuild_map_review_summary(session=db, map_id=map_obj.id)

    by_id_response = await client.get(f"{settings.API_V1_STR}/maps/{map_obj.id}")
    assert by_id_response.status_code == 200
    assert by_id_response.json()["review_summary"] == {
        "overall_avg": pytest.approx(4.5),
        "gameplay_avg": None,
        "visuals_avg": None,
        "reviews_count": 2,
        "gameplay_count": 0,
        "visuals_count": 0,
        "comments_count": 1,
        "updated_at": by_id_response.json()["review_summary"]["updated_at"],
    }

    by_name_response = await client.get(
        f"{settings.API_V1_STR}/maps/name/{map_obj.name}",
    )
    assert by_name_response.status_code == 200
    assert by_name_response.json()["review_summary"]["reviews_count"] == 2

    list_response = await client.get(
        f"{settings.API_V1_STR}/maps",
        params={"id": map_obj.id},
    )
    assert list_response.status_code == 200
    assert list_response.json()[0]["review_summary"]["comments_count"] == 1


@pytest.mark.asyncio
async def test_read_map_v1_returns_null_review_summary_without_reviews(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    map_obj = await _create_map(db, id=930214)

    response = await client.get(f"{settings.API_V1_STR}/maps/{map_obj.id}")

    assert response.status_code == 200
    assert response.json()["review_summary"] is None
