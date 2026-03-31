from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlmodel import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import Map, Player, Record, ServerGlobalapi
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
        await db.exec(delete(Record).where(Record.id == id))
        await db.commit()
    record = Record(
        id=id,
        steamid64=steamid64,
        server_id=server_id,
        mode_id=mode_id,
        map_id=map_id,
        stage=stage,
        time=Decimal(time),
        teleports=teleports,
        points=points,
        created_on=created_on or datetime(2026, 1, 1, tzinfo=UTC),
        updated_on=updated_on or datetime(2026, 1, 1, tzinfo=UTC),
        updated_by=steamid64,
        replay_id=replay_id,
        is_valid=is_valid,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


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


async def test_read_records_v1_list_and_detail(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    player_id = random_steamid64()
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
    assert payload["data"][0]["mode"] == "kz_timer"
    assert payload["data"][0]["tickrate"] == 128
    assert payload["data"][0]["time"] == 35.289
    assert payload["data"][0]["points"] == 420
    assert payload["data"][0]["replay_id"] == 123
    assert payload["data"][0]["is_valid"] is True

    detail_response = await client.get(f"{settings.API_V1_STR}/records/{record.uuid}")
    assert detail_response.status_code == 200
    assert detail_response.json()["uuid"] == str(record.uuid)


async def test_read_recent_records_v1_returns_nested_public_feed(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await db.exec(delete(Record))
    await db.commit()

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
        "tier": 6,
    }
    assert first_row["server"] == {
        "id": 980300,
        "name": "Record Test Server",
    }
    assert first_row["mode"] == {
        "id": 201,
        "name": "kz_simple",
    }
    assert first_row["stage"] == 2
    assert first_row["teleports"] == 3
    assert first_row["time"] == 25.0

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
            ("mode_ids", 200),
            ("mode_ids", 201),
            ("teleports_type", "PRO"),
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
    fastest_map_one = await _create_record(
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
            ("mode_ids", 200),
            ("mode_ids", 201),
            ("teleports_type", "NUB"),
        ],
    )
    assert response.status_code == 200
    payload = response.json()
    assert [(row["map_id"], row["stage"]) for row in payload] == [
        (980200, 0),
        (980201, 1),
    ]
    assert payload[0]["uuid"] == str(fastest_map_one.uuid)
    assert payload[1]["uuid"] == str(fastest_map_two.uuid)

    pro_response = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params=[
            ("steamid64", player_id),
            ("mode_ids", 200),
            ("mode_ids", 201),
            ("teleports_type", "PRO"),
        ],
    )
    assert [row["map_id"] for row in pro_response.json()] == [980200]

    ovr_server_filtered = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params=[
            ("steamid64", player_id),
            ("mode_ids", 200),
            ("mode_ids", 201),
            ("teleports_type", "OVR"),
            ("server_ids", 980301),
        ],
    )
    assert [row["map_id"] for row in ovr_server_filtered.json()] == [980201]


async def test_read_pb_records_v1_rejects_invalid_anchor_combinations(
    client: AsyncClient,
) -> None:
    both = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params=[
            ("map_id", 1),
            ("steamid64", random_steamid64()),
            ("mode_ids", 200),
            ("teleports_type", "OVR"),
        ],
    )
    assert both.status_code == 422

    neither = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params=[
            ("mode_ids", 200),
            ("teleports_type", "OVR"),
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
