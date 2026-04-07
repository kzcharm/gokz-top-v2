from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.models import (
    Ban,
    BanType,
    Map,
    Player,
    Record,
    RecordFilter,
    RecordPb,
    ServerGlobalapi,
)
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


async def _create_player(
    db: AsyncSession,
    *,
    steamid64: int,
    name: str,
    alias: str | None = None,
    avatar_hash: str | None = None,
    country: str | None = None,
) -> Player:
    await db.exec(delete(Player).where(Player.steamid64 == steamid64))
    await db.commit()
    player = Player(
        steamid64=steamid64,
        name=name,
        alias=alias,
        avatar_hash=avatar_hash,
        country=country,
    )
    db.add(player)
    await db.commit()
    await db.refresh(player)
    return player


async def _create_map(
    db: AsyncSession,
    *,
    id: int,
    name: str,
    difficulty: int = 4,
) -> Map:
    await db.exec(delete(Map).where(Map.id == id))
    await db.commit()
    map_obj = Map(
        id=id,
        name=name,
        filesize=123456,
        validated=True,
        difficulty=difficulty,
        approved_by_steamid64=76561198003275951,
    )
    db.add(map_obj)
    await db.commit()
    await db.refresh(map_obj)
    return map_obj


async def _create_server_globalapi(
    db: AsyncSession,
    *,
    id: int,
    name: str,
) -> ServerGlobalapi:
    await db.exec(delete(ServerGlobalapi).where(ServerGlobalapi.id == id))
    await db.commit()
    server = ServerGlobalapi(
        id=id,
        port=27015,
        ip=f"203.0.113.{id % 255}",
        name=name,
        owner_steamid64=76561198000000010,
        approval_status=1,
        approved_by_steamid64=76561198000000020,
    )
    db.add(server)
    await db.commit()
    await db.refresh(server)
    return server


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


async def _create_record(
    db: AsyncSession,
    *,
    id: int | None,
    steamid64: int,
    server_id: int,
    mode_id: int,
    map_id: int,
    stage: int,
    time: str,
    teleports: int,
    points: int = 0,
    is_valid: bool = True,
    replay_id: int | None = None,
    created_on: datetime | None = None,
    updated_on: datetime | None = None,
) -> Record:
    if id is not None:
        record_uuid_subquery = select(Record.uuid).where(Record.id == id)
        await db.exec(
            delete(RecordPb).where(RecordPb.record_uuid.in_(record_uuid_subquery))
        )
        await db.exec(delete(Record).where(Record.id == id))
        await db.commit()
    record, _created, _updated = await crud.upsert_record(
        session=db,
        record_id=id,
        record_uuid=None,
        steamid64=steamid64,
        server_id=server_id,
        mode_id=mode_id,
        map_id=map_id,
        stage=stage,
        time_seconds=Decimal(time),
        teleports=teleports,
        points=points,
        created_on=created_on or datetime(2026, 1, 1, tzinfo=UTC),
        updated_on=updated_on or datetime(2026, 1, 1, tzinfo=UTC),
        updated_by=steamid64,
        replay_id=replay_id,
        is_valid=is_valid,
    )
    await db.commit()
    await db.refresh(record)
    return record


async def _create_ban(
    db: AsyncSession,
    *,
    id: int,
    steamid64: int,
    expires_on: datetime | None,
) -> Ban:
    await db.exec(delete(Ban).where(Ban.id == id))
    await db.commit()
    ban = Ban(
        id=id,
        ban_type=BanType.BHOP_HACK,
        expires_on=expires_on,
        steamid64=steamid64,
        player_name=f"Player {steamid64}",
        notes="cheater",
        stats="stats",
        server_id=980300,
        updated_by_id="980300",
        created_on=datetime(2026, 1, 2, tzinfo=UTC),
        updated_on=datetime(2026, 1, 2, tzinfo=UTC),
    )
    db.add(ban)
    await db.commit()
    await db.refresh(ban)
    return ban


async def _seed_record_dependencies(
    db: AsyncSession,
    *,
    map_id: int = 980200,
    map_name: str = "kz_record_test",
    map_difficulty: int = 4,
    server_id: int = 980300,
    server_name: str = "Record Test Server",
    players: list[tuple[int, str]] | None = None,
) -> None:
    await _create_map(db, id=map_id, name=map_name, difficulty=map_difficulty)
    await _create_server_globalapi(db, id=server_id, name=server_name)
    for steamid64, name in players or []:
        await _create_player(db, steamid64=steamid64, name=name)


async def _clear_records(db: AsyncSession) -> None:
    await db.exec(delete(RecordPb))
    await db.exec(delete(Record))
    await db.commit()


async def test_read_records_v1_list_and_detail(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    player_id = 76561199012345678
    await _seed_record_dependencies(
        db,
        players=[(player_id, "Runner One")],
    )
    record = await _create_record(
        db,
        id=980400,
        steamid64=player_id,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="35.289",
        teleports=0,
        points=420,
        replay_id=123,
    )

    list_response = await client.get(
        f"{settings.API_V1_STR}/records/",
        params={"steamid64": player_id},
    )
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["count"] == 1
    assert payload["data"][0]["uuid"] == str(record.uuid)
    assert payload["data"][0]["id"] == 980400
    assert payload["data"][0]["steamid64"] == str(player_id)
    assert payload["data"][0]["player_name"] == "Runner One"
    assert payload["data"][0]["server_name"] == "Record Test Server"
    assert payload["data"][0]["mode_id"] == 200
    assert payload["data"][0]["mode"] == "KZT"
    assert payload["data"][0]["tickrate"] == 128
    assert payload["data"][0]["time"] == 35.289
    assert payload["data"][0]["points"] == 1000
    assert payload["data"][0]["replay_id"] == 123
    assert payload["data"][0]["is_valid"] is True

    detail_response = await client.get(f"{settings.API_V1_STR}/records/{record.uuid}")
    assert detail_response.status_code == 200
    assert detail_response.json()["uuid"] == str(record.uuid)
    assert detail_response.json()["points"] == 1000


async def test_read_recent_records_v1_returns_nested_public_feed(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await _clear_records(db)

    first_player_id = random_steamid64()
    second_player_id = random_steamid64()
    await _seed_record_dependencies(
        db,
        players=[
            (first_player_id, "Runner One"),
            (second_player_id, "Runner Two"),
        ],
        map_difficulty=6,
    )
    await _create_player(
        db,
        steamid64=first_player_id,
        name="Runner One",
        alias="Alias One",
        avatar_hash="a" * 40,
        country="DE",
    )

    oldest = await _create_record(
        db,
        id=980450,
        steamid64=first_player_id,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="20.000",
        teleports=0,
        points=300,
        created_on=datetime(2026, 3, 30, 12, 0, tzinfo=UTC),
        updated_on=datetime(2026, 3, 30, 12, 0, tzinfo=UTC),
    )
    newest = await _create_record(
        db,
        id=980451,
        steamid64=second_player_id,
        server_id=980300,
        mode_id=201,
        map_id=980200,
        stage=2,
        time="25.000",
        teleports=3,
        points=450,
        created_on=datetime(2026, 3, 30, 12, 2, tzinfo=UTC),
        updated_on=datetime(2026, 3, 30, 12, 2, tzinfo=UTC),
    )
    null_id = await _create_record(
        db,
        id=None,
        steamid64=first_player_id,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=1,
        time="24.000",
        teleports=1,
        points=325,
        created_on=datetime(2026, 3, 30, 12, 1, tzinfo=UTC),
        updated_on=datetime(2026, 3, 30, 12, 1, tzinfo=UTC),
    )
    await _create_record(
        db,
        id=980452,
        steamid64=second_player_id,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="19.000",
        teleports=0,
        points=500,
        is_valid=False,
        created_on=datetime(2026, 3, 30, 12, 3, tzinfo=UTC),
        updated_on=datetime(2026, 3, 30, 12, 3, tzinfo=UTC),
    )

    response = await client.get(
        f"{settings.API_V1_STR}/records/recent",
        params={"limit": 2},
    )
    assert response.status_code == 200

    payload = response.json()
    assert isinstance(payload["count"], int)
    assert payload["count"] >= len(payload["data"])
    assert [row["uuid"] for row in payload["data"]] == [
        str(newest.uuid),
        str(null_id.uuid),
    ]

    first_row = payload["data"][0]
    assert first_row["id"] == 980451
    assert first_row["player"] == {
        "steamid64": str(second_player_id),
        "name": "Runner Two",
        "alias": None,
        "avatar_hash": None,
        "country": None,
    }
    assert first_row["map"] == {
        "id": 980200,
        "name": "kz_record_test",
        "tier": 0,
    }
    assert first_row["server"] == {
        "id": 980300,
        "name": "Record Test Server",
    }
    assert first_row["mode"] == {
        "id": 201,
        "name": "SKZ",
    }
    assert first_row["stage"] == 2
    assert first_row["teleports"] == 3
    assert first_row["time"] == 25.0
    assert first_row["points"] == 1000

    offset_response = await client.get(
        f"{settings.API_V1_STR}/records/recent",
        params={"offset": 2, "limit": 2},
    )
    assert offset_response.status_code == 200
    offset_payload = offset_response.json()
    assert [row["uuid"] for row in offset_payload["data"]] == [str(oldest.uuid)]
    assert offset_payload["data"][0]["player"] == {
        "steamid64": str(first_player_id),
        "name": "Runner One",
        "alias": "Alias One",
        "avatar_hash": "a" * 40,
        "country": "DE",
    }


async def test_read_recent_records_v1_rejects_limit_above_max(
    client: AsyncClient,
) -> None:
    response = await client.get(
        f"{settings.API_V1_STR}/records/recent",
        params={"limit": 10001},
    )

    assert response.status_code == 422


async def test_read_recent_records_v1_scope_points_and_pro_filters(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    player_id = 76561199012345678
    await _seed_record_dependencies(db, players=[(player_id, "Filter Runner")])

    pb_pro = await _create_record(
        db,
        id=980460,
        steamid64=player_id,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="20.000",
        teleports=0,
        created_on=datetime(2026, 3, 30, 12, 0, tzinfo=UTC),
        updated_on=datetime(2026, 3, 30, 12, 0, tzinfo=UTC),
    )
    non_pb_nub = await _create_record(
        db,
        id=980461,
        steamid64=player_id,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="21.000",
        teleports=5,
        created_on=datetime(2026, 3, 30, 12, 1, tzinfo=UTC),
        updated_on=datetime(2026, 3, 30, 12, 1, tzinfo=UTC),
    )
    pb_nub = await _create_record(
        db,
        id=980462,
        steamid64=player_id,
        server_id=980300,
        mode_id=201,
        map_id=980200,
        stage=1,
        time="22.000",
        teleports=3,
        created_on=datetime(2026, 3, 30, 12, 2, tzinfo=UTC),
        updated_on=datetime(2026, 3, 30, 12, 2, tzinfo=UTC),
    )

    filtered = await client.get(
        f"{settings.API_V1_STR}/records/recent",
        params={"scope": "OVR", "points_more_or_equal_than": 1},
    )
    assert filtered.status_code == 200
    assert [row["id"] for row in filtered.json()["data"]] == [980462, 980460]

    pro_only = await client.get(
        f"{settings.API_V1_STR}/records/recent",
        params={
            "scope": "OVR",
            "points_more_or_equal_than": 1,
            "is_pro_only": True,
        },
    )
    assert pro_only.status_code == 200
    assert [row["id"] for row in pro_only.json()["data"]] == [pb_pro.id]

    all_recent = await client.get(
        f"{settings.API_V1_STR}/records/recent",
        params={"scope": "OVR"},
    )
    assert all_recent.status_code == 200
    points_by_id = {row["id"]: row["points"] for row in all_recent.json()["data"][:3]}
    assert points_by_id[pb_pro.id] == 1000
    assert points_by_id[pb_nub.id] == 1000
    assert points_by_id[non_pb_nub.id] == 0


async def test_patch_record_v1_updates_validity(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
    normal_user_token_headers: dict[str, str],
) -> None:
    player_id = random_steamid64()
    await _seed_record_dependencies(db, players=[(player_id, "Runner Patch")])
    record = await _create_record(
        db,
        id=980401,
        steamid64=player_id,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="40.000",
        teleports=0,
    )

    forbidden = await client.patch(
        f"{settings.API_V1_STR}/records/{record.uuid}",
        headers=normal_user_token_headers,
        json={"is_valid": False},
    )
    assert forbidden.status_code == 403

    response = await client.patch(
        f"{settings.API_V1_STR}/records/{record.uuid}",
        headers=superuser_token_headers,
        json={"is_valid": False},
    )
    assert response.status_code == 200
    assert response.json()["is_valid"] is False


async def test_read_pb_records_v1_map_anchor_returns_fastest_per_player_across_modes(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    player_one = random_steamid64()
    player_two = random_steamid64()
    await _seed_record_dependencies(
        db,
        players=[
            (player_one, "Runner Alpha"),
            (player_two, "Runner Beta"),
        ],
    )
    await _create_record(
        db,
        id=980410,
        steamid64=player_one,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="30.000",
        teleports=0,
    )
    winning = await _create_record(
        db,
        id=980411,
        steamid64=player_one,
        server_id=980300,
        mode_id=201,
        map_id=980200,
        stage=0,
        time="29.500",
        teleports=0,
        replay_id=9001,
    )
    await _create_record(
        db,
        id=980412,
        steamid64=player_two,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="31.000",
        teleports=0,
    )
    await _create_record(
        db,
        id=980413,
        steamid64=player_two,
        server_id=980300,
        mode_id=201,
        map_id=980200,
        stage=0,
        time="28.000",
        teleports=0,
        is_valid=False,
    )

    response = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params=[
            ("map_id", 980200),
            ("stage", 0),
            ("scope", "OVR"),
            ("is_pro_only", True),
        ],
    )
    assert response.status_code == 200
    payload = response.json()
    assert [row["player_name"] for row in payload] == ["Runner Alpha", "Runner Beta"]
    assert payload[0]["uuid"] == str(winning.uuid)
    assert payload[0]["mode_id"] == 201
    assert payload[0]["replay_id"] == 9001


async def test_read_pb_records_v1_player_anchor_and_filters(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    player_id = random_steamid64()
    await _seed_record_dependencies(
        db,
        players=[(player_id, "Runner Gamma")],
    )
    await _create_server_globalapi(db, id=980301, name="Secondary Server")
    await _create_record(
        db,
        id=980420,
        steamid64=player_id,
        server_id=980300,
        mode_id=201,
        map_id=980200,
        stage=0,
        time="25.000",
        teleports=1,
    )
    await _create_record(
        db,
        id=980421,
        steamid64=player_id,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="24.000",
        teleports=0,
    )
    await _create_map(db, id=980201, name="kz_record_bonus")
    fastest_map_two = await _create_record(
        db,
        id=980422,
        steamid64=player_id,
        server_id=980301,
        mode_id=200,
        map_id=980201,
        stage=1,
        time="50.000",
        teleports=1,
    )
    await _create_record(
        db,
        id=980423,
        steamid64=player_id,
        server_id=980301,
        mode_id=201,
        map_id=980201,
        stage=1,
        time="49.000",
        teleports=1,
        is_valid=False,
    )

    response = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params=[
            ("steamid64", player_id),
            ("scope", "OVR"),
            ("stage", 0),
        ],
    )
    assert response.status_code == 200
    payload = response.json()
    assert [(row["map_id"], row["stage"]) for row in payload] == [(980200, 0)]
    assert payload[0]["id"] == 980421
    assert payload[0]["map_tier"] == 4
    assert payload[0]["teleports"] == 0

    bonus_response = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params=[
            ("steamid64", player_id),
            ("scope", "OVR"),
            ("stage", 1),
        ],
    )
    assert bonus_response.status_code == 200
    bonus_payload = bonus_response.json()
    assert [(row["map_id"], row["stage"]) for row in bonus_payload] == [(980201, 1)]
    assert bonus_payload[0]["uuid"] == str(fastest_map_two.uuid)
    assert bonus_payload[0]["map_tier"] == 0

    pro_response = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params=[
            ("steamid64", player_id),
            ("scope", "OVR"),
            ("is_pro_only", True),
            ("stage", 0),
        ],
    )
    assert [row["map_id"] for row in pro_response.json()] == [980200]

    skz_response = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params=[
            ("steamid64", player_id),
            ("scope", "SKZ"),
            ("stage", 0),
        ],
    )
    assert [row["id"] for row in skz_response.json()] == [980420]


async def test_read_pb_records_v1_filters_by_country_and_region(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    player_one = random_steamid64()
    player_two = random_steamid64()
    player_three = random_steamid64()
    await _seed_record_dependencies(
        db,
        players=[
            (player_one, "Runner DE"),
            (player_two, "Runner FR"),
            (player_three, "Runner JP"),
        ],
    )
    await _create_player(db, steamid64=player_one, name="Runner DE", country="DE")
    await _create_player(db, steamid64=player_two, name="Runner FR", country="FR")
    await _create_player(db, steamid64=player_three, name="Runner JP", country="JP")
    await _create_record(
        db,
        id=980432,
        steamid64=player_one,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="20.000",
        teleports=0,
    )
    await _create_record(
        db,
        id=980433,
        steamid64=player_two,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="21.000",
        teleports=0,
    )
    await _create_record(
        db,
        id=980434,
        steamid64=player_three,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="22.000",
        teleports=0,
    )

    country_response = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params={
            "map_id": 980200,
            "scope": "OVR",
            "stage": 0,
            "country": "DE",
        },
    )
    assert country_response.status_code == 200
    assert [row["steamid64"] for row in country_response.json()] == [str(player_one)]

    region_response = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params={
            "map_id": 980200,
            "scope": "OVR",
            "stage": 0,
            "region": "EU",
        },
    )
    assert region_response.status_code == 200
    assert [row["steamid64"] for row in region_response.json()] == [
        str(player_one),
        str(player_two),
    ]


async def test_read_pb_records_v1_rejects_invalid_region_and_country_region_combo(
    client: AsyncClient,
) -> None:
    invalid_region = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params={
            "map_id": 1,
            "scope": "OVR",
            "region": "ZZ",
        },
    )
    assert invalid_region.status_code == 422

    both = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params={
            "map_id": 1,
            "scope": "OVR",
            "country": "DE",
            "region": "EU",
        },
    )
    assert both.status_code == 422


async def test_read_pb_records_v1_supports_offset_and_limit(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    player_one = random_steamid64()
    player_two = random_steamid64()
    player_three = random_steamid64()
    await _seed_record_dependencies(
        db,
        players=[
            (player_one, "Runner One"),
            (player_two, "Runner Two"),
            (player_three, "Runner Three"),
        ],
    )
    await _create_map(db, id=980202, name="kz_record_paging_a")
    await _create_map(db, id=980203, name="kz_record_paging_b")

    first = await _create_record(
        db,
        id=980424,
        steamid64=player_one,
        server_id=980300,
        mode_id=200,
        map_id=980202,
        stage=0,
        time="20.000",
        teleports=0,
    )
    second = await _create_record(
        db,
        id=980425,
        steamid64=player_two,
        server_id=980300,
        mode_id=200,
        map_id=980202,
        stage=0,
        time="21.000",
        teleports=0,
    )
    third = await _create_record(
        db,
        id=980426,
        steamid64=player_three,
        server_id=980300,
        mode_id=200,
        map_id=980202,
        stage=0,
        time="22.000",
        teleports=0,
    )
    await _create_record(
        db,
        id=980427,
        steamid64=player_one,
        server_id=980300,
        mode_id=200,
        map_id=980203,
        stage=0,
        time="30.000",
        teleports=0,
    )
    await _create_record(
        db,
        id=980428,
        steamid64=player_one,
        server_id=980300,
        mode_id=201,
        map_id=980203,
        stage=1,
        time="35.000",
        teleports=0,
    )

    map_response = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params=[
            ("map_id", 980202),
            ("stage", 0),
            ("scope", "OVR"),
            ("offset", 1),
            ("limit", 1),
        ],
    )
    assert map_response.status_code == 200
    assert [row["id"] for row in map_response.json()] == [second.id]

    player_response = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params=[
            ("steamid64", player_one),
            ("scope", "OVR"),
            ("offset", 1),
            ("limit", 1),
        ],
    )
    assert player_response.status_code == 200
    payload = player_response.json()
    assert len(payload) == 1
    assert payload[0]["map_id"] == 980203
    assert payload[0]["stage"] == 0
    assert payload[0]["id"] != first.id
    assert payload[0]["id"] != third.id


async def test_read_pb_records_v1_returns_scope_aware_course_tier(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    player_id = 76561199012345678
    map_id = 1_998_200
    server_id = 1_998_300
    await _seed_record_dependencies(
        db,
        map_id=map_id,
        map_name="kz_scope_tier",
        server_id=server_id,
        players=[(player_id, "Scoped Runner")],
    )
    record = await _create_record(
        db,
        id=980429,
        steamid64=player_id,
        server_id=server_id,
        mode_id=201,
        map_id=map_id,
        stage=0,
        time="24.500",
        teleports=0,
    )
    await _create_record_filter(
        db,
        id=981700,
        map_id=map_id,
        stage=0,
        mode_id=200,
        tier=7,
    )
    await _create_record_filter(
        db,
        id=981701,
        map_id=map_id,
        stage=0,
        mode_id=201,
        tier=2,
    )

    ovr_response = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params={"steamid64": str(player_id), "scope": "OVR"},
    )
    kzt_response = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params={"steamid64": str(player_id), "scope": "KZT"},
    )
    detail_response = await client.get(
        f"{settings.API_V1_STR}/records/{record.uuid}",
        params={"scope": "SKZ"},
    )

    assert ovr_response.status_code == 200
    assert ovr_response.json()[0]["map_tier"] == 2
    assert kzt_response.status_code == 200
    assert kzt_response.json() == []
    assert detail_response.status_code == 200
    assert detail_response.json()["map_tier"] == 2


async def test_read_pb_records_v1_rejects_invalid_anchor_combinations(
    client: AsyncClient,
) -> None:
    both = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params=[
            ("map_id", 1),
            ("steamid64", random_steamid64()),
            ("scope", "OVR"),
        ],
    )
    assert both.status_code == 422

    neither = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params=[
            ("scope", "OVR"),
        ],
    )
    assert neither.status_code == 422


async def test_read_record_v0_top_place_world_records_and_recent(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    player_one = random_steamid64()
    player_two = random_steamid64()
    await _seed_record_dependencies(
        db,
        players=[
            (player_one, "Compat One"),
            (player_two, "Compat Two"),
        ],
    )
    now = datetime(2026, 3, 1, tzinfo=UTC)
    await _create_record(
        db,
        id=980430,
        steamid64=player_one,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="19.500",
        teleports=0,
        created_on=now,
        updated_on=now,
    )
    await _create_record(
        db,
        id=980431,
        steamid64=player_two,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="20.000",
        teleports=0,
        created_on=now + timedelta(minutes=1),
        updated_on=now + timedelta(minutes=1),
    )
    await _create_record(
        db,
        id=980432,
        steamid64=player_two,
        server_id=980300,
        mode_id=201,
        map_id=980200,
        stage=0,
        time="22.000",
        teleports=1,
        created_on=now + timedelta(minutes=2),
        updated_on=now + timedelta(minutes=2),
    )
    await _create_record(
        db,
        id=980433,
        steamid64=player_one,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="18.000",
        teleports=0,
        is_valid=False,
        created_on=now + timedelta(minutes=3),
        updated_on=now + timedelta(minutes=3),
    )

    by_id = await client.get("/v0/records/980430")
    assert by_id.status_code == 200
    assert by_id.json()["player_name"] == "Compat One"
    assert by_id.json()["server"]["id"] == 980300

    place = await client.get("/v0/records/place/980431")
    assert place.status_code == 200
    assert place.json() == 2

    top = await client.get(
        "/v0/records/top",
        params=[
            ("map_id", 980200),
            ("stage", 0),
            ("modes_list", "kz_timer"),
            ("has_teleports", False),
        ],
    )
    assert top.status_code == 200
    assert [row["id"] for row in top.json()] == [980430, 980431]

    top_tickrate = await client.get(
        "/v0/records/top",
        params={"map_id": 980200, "tickrate": 64},
    )
    assert top_tickrate.status_code == 200
    assert top_tickrate.json() == []

    world_records = await client.get(
        "/v0/records/top/world_records",
        params=[("map_ids", 980200), ("mode_ids", 200)],
    )
    assert world_records.status_code == 200
    assert world_records.json() == [
        {
            "steamid64": player_one,
            "player_name": "Compat One",
            "steam_id": None,
            "world_records": 1,
        }
    ]

    recent = await client.get(
        "/v0/records/top/recent",
        params={
            "map_id": 980200,
            "created_since": (now - timedelta(minutes=1)).isoformat(),
            "place_top_at_least": 5,
        },
    )
    assert recent.status_code == 200
    recent_payload = recent.json()
    assert [row["id"] for row in recent_payload] == [980432, 980431, 980430]
    assert recent_payload[0]["top_100"] is True
    assert recent_payload[1]["place"] == 2


async def test_record_foreign_keys_and_nullable_globalapi_id_uniqueness(
    db: AsyncSession,
) -> None:
    player_id = random_steamid64()
    await _seed_record_dependencies(db, players=[(player_id, "FK Player")])

    await _create_record(
        db,
        id=980440,
        steamid64=player_id,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="60.000",
        teleports=0,
    )

    duplicate = Record(
        id=980440,
        steamid64=player_id,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time=Decimal("61.000"),
        teleports=0,
        updated_by=player_id,
        is_valid=True,
    )
    db.add(duplicate)
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()

    null_one = await _create_record(
        db,
        id=None,
        steamid64=player_id,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=1,
        time="70.000",
        teleports=0,
    )
    null_two = await _create_record(
        db,
        id=None,
        steamid64=player_id,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=2,
        time="80.000",
        teleports=0,
    )
    assert null_one.id is None
    assert null_two.id is None

    invalid_fk = Record(
        id=980441,
        steamid64=random_steamid64(),
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time=Decimal("65.000"),
        teleports=0,
        updated_by=player_id,
        is_valid=True,
    )
    db.add(invalid_fk)
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


async def test_read_records_v1_and_pb_exclude_cheaters_by_default(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    clean_player = random_steamid64()
    banned_player = random_steamid64()
    await _seed_record_dependencies(
        db,
        players=[
            (clean_player, "Clean"),
            (banned_player, "Banned"),
        ],
    )
    await _create_record(
        db,
        id=981000,
        steamid64=clean_player,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="20.000",
        teleports=0,
        created_on=datetime(2026, 3, 1, tzinfo=UTC),
        updated_on=datetime(2026, 3, 1, tzinfo=UTC),
    )
    await _create_record(
        db,
        id=981001,
        steamid64=banned_player,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="10.000",
        teleports=0,
        created_on=datetime(2026, 3, 2, tzinfo=UTC),
        updated_on=datetime(2026, 3, 2, tzinfo=UTC),
    )
    await _create_ban(db, id=981100, steamid64=banned_player, expires_on=None)

    listed = await client.get(
        f"{settings.API_V1_STR}/records/",
        params={"map_id": 980200},
    )
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()["data"]] == [981000]

    listed_all = await client.get(
        f"{settings.API_V1_STR}/records/",
        params={"map_id": 980200, "exclude_cheaters": "false"},
    )
    assert listed_all.status_code == 200
    assert [row["id"] for row in listed_all.json()["data"]] == [981001, 981000]

    pb = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params={"map_id": 980200, "scope": "OVR", "exclude_cheaters": "true"},
    )
    assert pb.status_code == 200
    assert [row["id"] for row in pb.json()] == [981000]

    pb_all = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params={"map_id": 980200, "scope": "OVR", "exclude_cheaters": "false"},
    )
    assert pb_all.status_code == 200
    assert [row["id"] for row in pb_all.json()] == [981001, 981000]


async def test_read_records_recent_still_includes_banned_players(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await _clear_records(db)
    banned_player = random_steamid64()
    await _seed_record_dependencies(db, players=[(banned_player, "Recent Banned")])
    record = await _create_record(
        db,
        id=981010,
        steamid64=banned_player,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="15.000",
        teleports=0,
        created_on=datetime(2030, 3, 3, tzinfo=UTC),
        updated_on=datetime(2030, 3, 3, tzinfo=UTC),
    )
    await _create_ban(db, id=981110, steamid64=banned_player, expires_on=None)

    response = await client.get(f"{settings.API_V1_STR}/records/recent")
    assert response.status_code == 200
    assert record.id in [row["id"] for row in response.json()["data"]]


async def test_read_record_v0_top_and_world_records_exclude_cheaters_by_default(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    banned_player = random_steamid64()
    clean_player = random_steamid64()
    await _seed_record_dependencies(
        db,
        players=[
            (banned_player, "Banned"),
            (clean_player, "Clean"),
        ],
    )
    now = datetime(2026, 3, 5, tzinfo=UTC)
    await _create_record(
        db,
        id=981020,
        steamid64=banned_player,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="12.000",
        teleports=0,
        created_on=now,
        updated_on=now,
    )
    await _create_record(
        db,
        id=981021,
        steamid64=clean_player,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="18.000",
        teleports=0,
        created_on=now + timedelta(minutes=1),
        updated_on=now + timedelta(minutes=1),
    )
    await _create_ban(db, id=981120, steamid64=banned_player, expires_on=None)

    top = await client.get(
        "/v0/records/top",
        params={"map_id": 980200, "stage": 0, "modes_list": "kz_timer", "has_teleports": False},
    )
    assert top.status_code == 200
    assert [row["id"] for row in top.json()] == [981021]

    top_all = await client.get(
        "/v0/records/top",
        params={
            "map_id": 980200,
            "stage": 0,
            "modes_list": "kz_timer",
            "has_teleports": False,
            "exclude_cheaters": "false",
        },
    )
    assert top_all.status_code == 200
    assert [row["id"] for row in top_all.json()] == [981020, 981021]

    world_records = await client.get(
        "/v0/records/top/world_records",
        params={"map_ids": 980200, "mode_ids": 200},
    )
    assert world_records.status_code == 200
    assert world_records.json() == [
        {
            "steamid64": clean_player,
            "player_name": "Clean",
            "steam_id": None,
            "world_records": 1,
        }
    ]

    world_records_all = await client.get(
        "/v0/records/top/world_records",
        params={"map_ids": 980200, "mode_ids": 200, "exclude_cheaters": "false"},
    )
    assert world_records_all.status_code == 200
    assert world_records_all.json()[0]["steamid64"] == banned_player
