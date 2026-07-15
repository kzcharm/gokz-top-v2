import math
import uuid
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
    MapCourse,
    MapCourseTier,
    ModeScope,
    Player,
    Record,
    RecordBulkDeleteCourse,
    RecordFilter,
    RecordModerationAction,
    RecordModerationActionRecord,
    RecordModerationActionType,
    RecordPb,
    RecordType,
    ServerGlobalapi,
    legacy_mode_id_to_kz_mode,
)
from app.services.run_replay_storage import save_run_replay
from tests.utils.server import create_server_group
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


async def _create_player(
    db: AsyncSession,
    *,
    steamid64: int,
    name: str,
    alias: str | None = None,
    custom_id: str | None = None,
    avatar_hash: str | None = None,
    country: str | None = None,
) -> Player:
    await db.exec(delete(Player).where(Player.steamid64 == steamid64))
    await db.commit()
    player = Player(
        steamid64=steamid64,
        name=name,
        alias=alias,
        custom_id=custom_id,
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
    workshop_id: int | None = None,
) -> Map:
    await db.exec(delete(Map).where(Map.id == id))
    await db.commit()
    map_obj = Map(
        id=id,
        name=name,
        filesize=123456,
        validated=True,
        difficulty=difficulty,
        workshop_id=workshop_id,
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
    group_id: uuid.UUID | None = None,
) -> ServerGlobalapi:
    await db.exec(delete(ServerGlobalapi).where(ServerGlobalapi.id == id))
    await db.commit()
    for steamid64 in (76561198000000010, 76561198000000020):

        if await db.get(Player, steamid64) is None:

            db.add(Player(steamid64=steamid64, name=str(steamid64)))

    server = ServerGlobalapi(
        id=id,
        port=27015,
        ip=f"203.0.113.{id % 255}",
        name=name,
        owner_steamid64=76561198000000010,
        approval_status=1,
        approved_by_steamid64=76561198000000020,
        group_id=group_id,
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
    map_workshop_id: int | None = None,
    server_id: int = 980300,
    server_name: str = "Record Test Server",
    server_group_id: uuid.UUID | None = None,
    players: list[tuple[int, str]] | None = None,
) -> None:
    await _create_map(
        db,
        id=map_id,
        name=map_name,
        difficulty=map_difficulty,
        workshop_id=map_workshop_id,
    )
    await _create_server_globalapi(
        db,
        id=server_id,
        name=server_name,
        group_id=server_group_id,
    )
    for steamid64, name in players or []:
        await _create_player(db, steamid64=steamid64, name=name)


async def _clear_records(db: AsyncSession) -> None:
    await db.exec(delete(RecordPb))
    await db.exec(delete(Record))
    await db.commit()


async def test_read_records_v1_list_and_detail(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(settings, "REPLAY_STORAGE_DIR", tmp_path)
    player_id = 76561199012345678
    server_group, _ = await create_server_group(
        db,
        name="Record Test Group",
    )
    await _seed_record_dependencies(
        db,
        server_group_id=server_group.id,
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
    save_run_replay(map_name="kz_record_test", replay_id=record.uuid, replay_bytes=b"run")

    list_response = await client.get(
        f"{settings.API_V1_STR}/records",
        params={"steamid64": player_id},
    )
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["count"] == 1
    assert payload["data"][0]["uuid"] == str(record.uuid)
    assert payload["data"][0]["id"] == 980400
    assert payload["data"][0]["player"] == {
        "steamid64": str(player_id),
        "display_name": "Runner One",
    }
    assert payload["data"][0]["server_name"] == "Record Test Server"
    assert payload["data"][0]["server_group"] == {
        "id": str(server_group.id),
        "name": "Record Test Group",
        "custom_id": server_group.custom_id,
    }
    assert payload["data"][0]["mode_id"] == 200
    assert payload["data"][0]["mode"] == "KZT"
    assert payload["data"][0]["tickrate"] == 128
    assert payload["data"][0]["time"] == 35.289
    assert payload["data"][0]["points"] == 1000
    assert payload["data"][0]["replay_id"] == 123
    assert payload["data"][0]["is_replay_available"] is True
    assert payload["data"][0]["is_valid"] is True

    detail_response = await client.get(f"{settings.API_V1_STR}/records/{record.uuid}")
    assert detail_response.status_code == 200
    assert detail_response.json()["uuid"] == str(record.uuid)
    assert detail_response.json()["points"] == 1000
    assert detail_response.json()["server_group"]["custom_id"] == server_group.custom_id
    assert detail_response.json()["is_replay_available"] is True


async def test_read_recent_records_v1_returns_nested_public_feed(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(settings, "REPLAY_STORAGE_DIR", tmp_path)
    await _clear_records(db)

    first_player_id = random_steamid64()
    second_player_id = random_steamid64()
    server_group, _ = await create_server_group(
        db,
        name="Recent Record Group",
    )
    await _seed_record_dependencies(
        db,
        players=[
            (first_player_id, "Runner One"),
            (second_player_id, "Runner Two"),
        ],
        map_difficulty=6,
        server_group_id=server_group.id,
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
        "display_name": "Runner Two",
    }
    assert first_row["map"] == {
        "id": 980200,
        "name": "kz_record_test",
        "tier": 0,
    }
    assert first_row["server"] == {
        "id": 980300,
        "name": "Record Test Server",
        "group": {
            "id": str(server_group.id),
            "name": "Recent Record Group",
            "custom_id": server_group.custom_id,
        },
    }
    assert first_row["mode"] == {
        "id": 201,
        "name": "SKZ",
    }
    assert first_row["stage"] == 2
    assert first_row["teleports"] == 3
    assert first_row["time"] == 25.0
    assert first_row["points"] == 1000
    assert first_row["is_replay_available"] is False

    offset_response = await client.get(
        f"{settings.API_V1_STR}/records/recent",
        params={"offset": 2, "limit": 2},
    )
    assert offset_response.status_code == 200
    offset_payload = offset_response.json()
    assert [row["uuid"] for row in offset_payload["data"]] == [str(oldest.uuid)]
    assert offset_payload["data"][0]["player"] == {
        "steamid64": str(first_player_id),
        "display_name": "Alias One",
    }


async def test_read_recent_records_v1_rejects_limit_above_max(
    client: AsyncClient,
) -> None:
    response = await client.get(
        f"{settings.API_V1_STR}/records/recent",
        params={"limit": 100001},
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
            "type": "PRO",
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


async def test_read_recent_records_v1_filters_by_record_context(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await _clear_records(db)
    player_id = random_steamid64()
    await _seed_record_dependencies(db, players=[(player_id, "Context Runner")])
    await _create_map(db, id=980201, name="kz_recent_beta", difficulty=7)
    await _create_record_filter(
        db,
        id=980501,
        map_id=980200,
        stage=0,
        mode_id=200,
        tier=4,
    )
    await _create_record_filter(
        db,
        id=980502,
        map_id=980200,
        stage=2,
        mode_id=201,
        tier=6,
    )
    await _create_record_filter(
        db,
        id=980503,
        map_id=980201,
        stage=0,
        mode_id=200,
        tier=7,
    )

    pro_record = await _create_record(
        db,
        id=980470,
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
    skz_nub_record = await _create_record(
        db,
        id=980471,
        steamid64=player_id,
        server_id=980300,
        mode_id=201,
        map_id=980200,
        stage=2,
        time="21.000",
        teleports=4,
        created_on=datetime(2026, 3, 30, 12, 1, tzinfo=UTC),
        updated_on=datetime(2026, 3, 30, 12, 1, tzinfo=UTC),
    )
    beta_nub_record = await _create_record(
        db,
        id=980472,
        steamid64=player_id,
        server_id=980300,
        mode_id=200,
        map_id=980201,
        stage=0,
        time="22.000",
        teleports=5,
        created_on=datetime(2026, 3, 30, 12, 2, tzinfo=UTC),
        updated_on=datetime(2026, 3, 30, 12, 2, tzinfo=UTC),
    )
    non_pb_record = await _create_record(
        db,
        id=980473,
        steamid64=player_id,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="23.000",
        teleports=6,
        created_on=datetime(2026, 3, 30, 12, 3, tzinfo=UTC),
        updated_on=datetime(2026, 3, 30, 12, 3, tzinfo=UTC),
    )

    for record, record_type, points in (
        (pro_record, RecordType.PRO, 1000),
        (skz_nub_record, RecordType.NUB, 850),
        (beta_nub_record, RecordType.NUB, 950),
    ):
        record_pb = (
            await db.exec(
                select(RecordPb).where(
                    RecordPb.record_uuid == record.uuid,
                    RecordPb.scope == ModeScope.OVR,
                    RecordPb.type == record_type,
                )
            )
        ).one()
        record_pb.points = points
        db.add(record_pb)
    await db.commit()

    cases: list[tuple[dict[str, str | int], list[int | None]]] = [
        ({"mode": "SKZ"}, [skz_nub_record.id]),
        ({"map_id": 980201}, [beta_nub_record.id]),
        ({"stage": 2}, [skz_nub_record.id]),
        ({"is_bonus": "true"}, [skz_nub_record.id]),
        ({"is_bonus": "false"}, [non_pb_record.id, beta_nub_record.id, pro_record.id]),
        ({"tier": 6}, [skz_nub_record.id]),
        ({"type": "PRO"}, [pro_record.id]),
        (
            {"points_more_or_equal_than": 800, "points_less_or_equal_than": 899},
            [skz_nub_record.id],
        ),
        (
            {"points_more_or_equal_than": 900, "points_less_or_equal_than": 999},
            [beta_nub_record.id],
        ),
        (
            {"points_more_or_equal_than": 1000, "points_less_or_equal_than": 1000},
            [pro_record.id],
        ),
        (
            {
                "mode": "SKZ",
                "map_id": 980200,
                "stage": 2,
                "tier": 6,
                "type": "NUB",
                "points_more_or_equal_than": 800,
                "points_less_or_equal_than": 899,
            },
            [skz_nub_record.id],
        ),
    ]

    for params, expected_ids in cases:
        response = await client.get(
            f"{settings.API_V1_STR}/records/recent",
            params=params,
        )
        assert response.status_code == 200
        payload = response.json()
        assert [row["id"] for row in payload["data"]] == expected_ids
        assert payload["count"] == len(expected_ids)

    positive_response = await client.get(
        f"{settings.API_V1_STR}/records/recent",
        params={"points_more_or_equal_than": 1},
    )
    assert positive_response.status_code == 200
    positive_ids = [row["id"] for row in positive_response.json()["data"]]
    assert non_pb_record.id not in positive_ids


async def test_read_recent_records_v1_rejects_invalid_filter_bounds(
    client: AsyncClient,
) -> None:
    for params in (
        {"map_id": 0},
        {"stage": -1},
        {"tier": 9},
        {"points_less_or_equal_than": 1001},
    ):
        response = await client.get(
            f"{settings.API_V1_STR}/records/recent",
            params=params,
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

    action = (
        await db.exec(select(RecordModerationAction))
    ).one()
    assert action.actor_steamid64 == settings.SUPER_USER_STEAMID64
    assert action.action_type == RecordModerationActionType.SINGLE_SOFT_DELETE
    assert action.target_record_uuid == record.uuid

    action_record = (
        await db.exec(select(RecordModerationActionRecord))
    ).one()
    assert action_record.record_uuid == record.uuid
    assert action_record.before_snapshot is not None
    assert action_record.after_snapshot is not None
    assert action_record.before_snapshot["is_valid"] is True
    assert action_record.after_snapshot["is_valid"] is False


async def test_patch_record_v1_allows_admin_role(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    player_id = random_steamid64()
    await _seed_record_dependencies(db, players=[(player_id, "Runner Admin Patch")])
    record = await _create_record(
        db,
        id=980402,
        steamid64=player_id,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="41.000",
        teleports=0,
    )
    admin_auth = await client.post(
        f"{settings.API_V1_STR}/private/auth/session",
        json={
            "steamid64": random_steamid64(),
            "roles": ["admin"],
            "is_active": True,
            "name": "Admin Record Moderator",
        },
    )
    admin_headers = {
        "Authorization": f"Bearer {admin_auth.json()['access_token']}"
    }

    response = await client.patch(
        f"{settings.API_V1_STR}/records/{record.uuid}",
        headers=admin_headers,
        json={"is_valid": False},
    )

    assert response.status_code == 200
    assert response.json()["is_valid"] is False


async def test_bulk_delete_course_records_soft_deletes_all_valid_matching_rows(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    player_id = random_steamid64()
    other_player_id = random_steamid64()
    await _seed_record_dependencies(
        db,
        players=[
            (player_id, "Bulk Delete Runner"),
            (other_player_id, "Other Runner"),
        ],
    )
    first = await _create_record(
        db,
        id=980470,
        steamid64=player_id,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="42.000",
        teleports=0,
    )
    second = await _create_record(
        db,
        id=980471,
        steamid64=player_id,
        server_id=980300,
        mode_id=201,
        map_id=980200,
        stage=0,
        time="43.000",
        teleports=2,
    )
    unaffected_stage = await _create_record(
        db,
        id=980472,
        steamid64=player_id,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=1,
        time="44.000",
        teleports=0,
    )
    unaffected_player = await _create_record(
        db,
        id=980473,
        steamid64=other_player_id,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="45.000",
        teleports=0,
    )

    response = await client.post(
        f"{settings.API_V1_STR}/records/bulk-delete-course",
        headers=superuser_token_headers,
        json=RecordBulkDeleteCourse(
            steamid64=str(player_id),
            map_id=980200,
            stage=0,
        ).model_dump(mode="json"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert {row["uuid"] for row in payload["data"]} == {
        str(first.uuid),
        str(second.uuid),
    }
    assert all(row["is_valid"] is False for row in payload["data"])

    refreshed_first = await db.get(Record, first.uuid)
    refreshed_second = await db.get(Record, second.uuid)
    refreshed_unaffected_stage = await db.get(Record, unaffected_stage.uuid)
    refreshed_unaffected_player = await db.get(Record, unaffected_player.uuid)
    assert refreshed_first is not None and refreshed_first.is_valid is False
    assert refreshed_second is not None and refreshed_second.is_valid is False
    assert (
        refreshed_unaffected_stage is not None
        and refreshed_unaffected_stage.is_valid is True
    )
    assert (
        refreshed_unaffected_player is not None
        and refreshed_unaffected_player.is_valid is True
    )

    action = (
        await db.exec(select(RecordModerationAction))
    ).one()
    assert action.action_type == RecordModerationActionType.BULK_SOFT_DELETE_COURSE
    assert action.target_player_steamid64 == player_id
    assert action.target_map_id == 980200
    assert action.target_stage == 0

    action_records = (
        await db.exec(
            select(RecordModerationActionRecord).order_by(
                RecordModerationActionRecord.record_id
            )
        )
    ).all()
    assert [row.record_uuid for row in action_records] == [first.uuid, second.uuid]
    assert all(row.before_snapshot is not None for row in action_records)
    assert all(row.after_snapshot is not None for row in action_records)
    assert all(row.before_snapshot["is_valid"] is True for row in action_records)
    assert all(row.after_snapshot["is_valid"] is False for row in action_records)


async def test_read_pb_records_v1_map_anchor_returns_fastest_per_player_across_modes(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(settings, "REPLAY_STORAGE_DIR", tmp_path)
    player_one = random_steamid64()
    player_two = random_steamid64()
    await _seed_record_dependencies(
        db,
        map_workshop_id=1986459033,
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
    save_run_replay(map_name="kz_record_test", replay_id=winning.uuid, replay_bytes=b"pb")

    response = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params=[
            ("map_id", 980200),
            ("stage", 0),
            ("scope", "OVR"),
            ("type", "PRO"),
        ],
    )
    assert response.status_code == 200
    payload = response.json()
    assert [row["player"]["display_name"] for row in payload] == [
        "Runner Alpha",
        "Runner Beta",
    ]
    assert payload[0]["uuid"] == str(winning.uuid)
    assert payload[0]["workshop_id"] == 1986459033
    assert payload[0]["mode_id"] == 201
    assert payload[0]["replay_id"] == 9001
    assert payload[0]["is_replay_available"] is True


async def test_read_record_run_history_v1_marks_pbs_and_wr_gap(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(settings, "REPLAY_STORAGE_DIR", tmp_path)
    player_id = random_steamid64()
    wr_player_id = random_steamid64()
    await _seed_record_dependencies(
        db,
        players=[
            (player_id, "History Runner"),
            (wr_player_id, "WR Runner"),
        ],
    )
    await _create_record(
        db,
        id=980414,
        steamid64=wr_player_id,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="80.000",
        teleports=0,
        created_on=datetime(2025, 12, 31, tzinfo=UTC),
    )
    first = await _create_record(
        db,
        id=980415,
        steamid64=player_id,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="100.000",
        teleports=0,
        created_on=datetime(2026, 1, 1, tzinfo=UTC),
    )
    slower = await _create_record(
        db,
        id=980416,
        steamid64=player_id,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="110.000",
        teleports=2,
        created_on=datetime(2026, 1, 2, tzinfo=UTC),
    )
    improved = await _create_record(
        db,
        id=980417,
        steamid64=player_id,
        server_id=980300,
        mode_id=201,
        map_id=980200,
        stage=0,
        time="95.000",
        teleports=0,
        created_on=datetime(2026, 1, 3, tzinfo=UTC),
    )
    save_run_replay(
        map_name="kz_record_test",
        replay_id=improved.uuid,
        replay_bytes=b"run",
    )

    response = await client.get(
        f"{settings.API_V1_STR}/records/run-history",
        params={
            "identifier": str(player_id),
            "map_id": 980200,
            "stage": 0,
            "scope": "OVR",
            "type": "NUB",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 3
    assert payload["wr_time"] == 80.0
    assert [row["uuid"] for row in payload["data"]] == [
        str(first.uuid),
        str(slower.uuid),
        str(improved.uuid),
    ]
    assert [row["is_pb"] for row in payload["data"]] == [True, False, True]
    assert payload["data"][0]["wr_gap"] == -2.0
    assert payload["data"][1]["wr_gap"] == pytest.approx(
        round(math.log2(110 / 80 - 1), 3)
    )
    assert payload["data"][2]["wr_gap"] == pytest.approx(
        round(math.log2(95 / 80 - 1), 3)
    )
    assert payload["data"][2]["mode"] == "SKZ"
    assert payload["data"][2]["is_replay_available"] is True


async def test_read_record_run_history_v1_pro_filters_zero_teleport_runs(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    player_id = random_steamid64()
    await _seed_record_dependencies(
        db,
        players=[(player_id, "PRO History Runner")],
    )
    pro_run = await _create_record(
        db,
        id=980418,
        steamid64=player_id,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="100.000",
        teleports=0,
        created_on=datetime(2026, 1, 1, tzinfo=UTC),
    )
    await _create_record(
        db,
        id=980419,
        steamid64=player_id,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="90.000",
        teleports=1,
        created_on=datetime(2026, 1, 2, tzinfo=UTC),
    )

    response = await client.get(
        f"{settings.API_V1_STR}/records/run-history",
        params={
            "identifier": str(player_id),
            "map_id": 980200,
            "scope": "OVR",
            "type": "PRO",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert [row["uuid"] for row in payload["data"]] == [str(pro_run.uuid)]
    assert payload["data"][0]["teleports"] == 0
    assert payload["data"][0]["wr_gap"] is None


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
    fastest_stage_zero = await _create_record(
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
    for pb_row in (
        await db.exec(
            select(RecordPb).where(RecordPb.record_uuid == fastest_stage_zero.uuid)
        )
    ).all():
        pb_row.raw_rating_contribution = 123
        db.add(pb_row)
    await db.commit()

    response = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params=[
            ("identifier", str(player_id)),
            ("scope", "OVR"),
            ("stage", 0),
        ],
    )
    assert response.status_code == 200
    payload = response.json()
    assert [(row["map_id"], row["stage"]) for row in payload] == [(980200, 0)]
    assert payload[0]["id"] == 980421
    assert payload[0]["map_tier"] == 0
    assert payload[0]["teleports"] == 0
    assert payload[0]["raw_rating_contribution"] == 123

    bonus_response = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params=[
            ("identifier", str(player_id)),
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
            ("identifier", str(player_id)),
            ("scope", "OVR"),
            ("type", "PRO"),
            ("stage", 0),
        ],
    )
    assert [row["map_id"] for row in pro_response.json()] == [980200]

    skz_response = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params=[
            ("identifier", str(player_id)),
            ("scope", "SKZ"),
            ("stage", 0),
        ],
    )
    assert [row["id"] for row in skz_response.json()] == [980420]


async def test_read_pb_records_v1_player_anchor_excludes_invalidated_maps(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    player_id = random_steamid64()
    await _seed_record_dependencies(
        db,
        players=[(player_id, "Valid Map Runner")],
    )
    await _create_map(db, id=980202, name="kz_record_invalidated")
    await _create_record(
        db,
        id=980426,
        steamid64=player_id,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="24.000",
        teleports=0,
    )
    await _create_record(
        db,
        id=980427,
        steamid64=player_id,
        server_id=980300,
        mode_id=200,
        map_id=980202,
        stage=0,
        time="23.000",
        teleports=0,
    )
    invalidated_map = await db.get(Map, 980202)
    assert invalidated_map is not None
    invalidated_map.validated = False
    db.add(invalidated_map)
    await db.commit()
    assert (
        await db.exec(select(Map.validated).where(Map.id == 980202))
    ).one() is False

    response = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params=[
            ("identifier", str(player_id)),
            ("scope", "OVR"),
            ("stage", 0),
        ],
    )

    assert response.status_code == 200
    assert [row["map_id"] for row in response.json()] == [980200]


async def test_read_pb_records_v1_uses_nub_points_when_type_is_nub(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    pro_player = random_steamid64()
    nub_player = random_steamid64()
    await _seed_record_dependencies(
        db,
        players=[
            (pro_player, "Pro Runner"),
            (nub_player, "Nub Leader"),
        ],
    )

    nub_leader = await _create_record(
        db,
        id=980424,
        steamid64=nub_player,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="19.000",
        teleports=5,
    )
    dual_pb_record = await _create_record(
        db,
        id=980425,
        steamid64=pro_player,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="20.000",
        teleports=0,
    )

    nub_response = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params=[
            ("map_id", 980200),
            ("stage", 0),
            ("scope", "OVR"),
            ("type", "NUB"),
        ],
    )
    assert nub_response.status_code == 200
    nub_payload = nub_response.json()
    assert [row["id"] for row in nub_payload] == [nub_leader.id, dual_pb_record.id]
    assert nub_payload[0]["points"] == 1000
    assert 1 <= nub_payload[1]["points"] < 1000

    pro_response = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params=[
            ("map_id", 980200),
            ("stage", 0),
            ("scope", "OVR"),
            ("type", "PRO"),
        ],
    )
    assert pro_response.status_code == 200
    pro_payload = pro_response.json()
    assert [row["id"] for row in pro_payload] == [dual_pb_record.id]
    assert pro_payload[0]["points"] == 1000


async def test_read_pb_records_v1_map_anchor_sorts_by_points(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    first_player = random_steamid64()
    second_player = random_steamid64()
    third_player = random_steamid64()
    await _seed_record_dependencies(
        db,
        players=[
            (first_player, "Points One"),
            (second_player, "Points Two"),
            (third_player, "Points Three"),
        ],
    )
    first = await _create_record(
        db,
        id=981440,
        steamid64=first_player,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="20.000",
        teleports=0,
    )
    second = await _create_record(
        db,
        id=981441,
        steamid64=second_player,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="21.000",
        teleports=0,
    )
    third = await _create_record(
        db,
        id=981442,
        steamid64=third_player,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="22.000",
        teleports=0,
    )
    for record, points in ((first, 100), (second, 900), (third, 500)):
        pb_rows = (
            await db.exec(
                select(RecordPb).where(
                    RecordPb.record_uuid == record.uuid,
                    RecordPb.scope == ModeScope.OVR,
                    RecordPb.type == RecordType.NUB,
                )
            )
        ).all()
        for pb_row in pb_rows:
            pb_row.points = points
            db.add(pb_row)
    await db.commit()

    response = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params={
            "map_id": 980200,
            "scope": "OVR",
            "stage": 0,
            "sort_by": "points",
            "sort_order": "desc",
        },
    )

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [
        second.id,
        third.id,
        first.id,
    ]


async def test_read_pb_records_v1_sorts_by_raw_rating_contribution(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    first_player = random_steamid64()
    second_player = random_steamid64()
    third_player = random_steamid64()
    await _seed_record_dependencies(
        db,
        players=[
            (first_player, "Rating One"),
            (second_player, "Rating Two"),
            (third_player, "Rating Three"),
        ],
    )
    first = await _create_record(
        db,
        id=981443,
        steamid64=first_player,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="20.000",
        teleports=0,
    )
    second = await _create_record(
        db,
        id=981444,
        steamid64=second_player,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="21.000",
        teleports=0,
    )
    third = await _create_record(
        db,
        id=981445,
        steamid64=third_player,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="22.000",
        teleports=0,
    )
    for record, contribution in ((first, 30), (second, 10), (third, 20)):
        pb_rows = (
            await db.exec(
                select(RecordPb).where(
                    RecordPb.record_uuid == record.uuid,
                    RecordPb.scope == ModeScope.OVR,
                    RecordPb.type == RecordType.NUB,
                )
            )
        ).all()
        for pb_row in pb_rows:
            pb_row.raw_rating_contribution = contribution
            db.add(pb_row)
    await db.commit()

    response = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params={
            "map_id": 980200,
            "scope": "OVR",
            "stage": 0,
            "sort_by": "raw_rating_contribution",
        },
    )

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [
        first.id,
        third.id,
        second.id,
    ]


async def test_read_pb_records_v1_player_anchor_sorts_by_created_at(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    player_id = random_steamid64()
    await _seed_record_dependencies(
        db,
        players=[(player_id, "Created Sort Runner")],
    )
    await _create_map(db, id=981204, name="kz_record_created_old")
    await _create_map(db, id=981205, name="kz_record_created_new")
    old_record = await _create_record(
        db,
        id=981446,
        steamid64=player_id,
        server_id=980300,
        mode_id=200,
        map_id=981204,
        stage=0,
        time="20.000",
        teleports=0,
        created_on=datetime(2026, 1, 1, tzinfo=UTC),
    )
    new_record = await _create_record(
        db,
        id=981447,
        steamid64=player_id,
        server_id=980300,
        mode_id=200,
        map_id=981205,
        stage=0,
        time="30.000",
        teleports=0,
        created_on=datetime(2026, 2, 1, tzinfo=UTC),
    )

    response = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params={
            "identifier": str(player_id),
            "scope": "OVR",
            "stage": 0,
            "sort_by": "created_at",
            "sort_order": "desc",
        },
    )

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [new_record.id, old_record.id]


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
    assert [row["player"]["steamid64"] for row in country_response.json()] == [
        str(player_one)
    ]

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
    assert [row["player"]["steamid64"] for row in region_response.json()] == [
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
            ("identifier", str(player_one)),
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
        params={"identifier": str(player_id), "scope": "OVR"},
    )
    kzt_response = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params={"identifier": str(player_id), "scope": "KZT"},
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
    conflicting_map_filters = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params=[
            ("map_id", 1),
            ("map_name", "kz_conflict"),
            ("scope", "OVR"),
        ],
    )
    assert conflicting_map_filters.status_code == 422

    neither = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params=[
            ("scope", "OVR"),
        ],
    )
    assert neither.status_code == 422


async def test_read_pb_records_v1_rejects_invalid_sort_by(
    client: AsyncClient,
) -> None:
    response = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params={
            "map_id": 1,
            "scope": "OVR",
            "sort_by": "rank",
        },
    )

    assert response.status_code == 422


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


async def test_read_record_v0_top_accepts_steam_id_and_filters_player_pbs(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    player_id = 76561199960265726
    await _seed_record_dependencies(
        db,
        players=[(player_id, "Steam2 Runner")],
    )
    await _create_record(
        db,
        id=980434,
        steamid64=player_id,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="19.500",
        teleports=2,
        points=100,
    )
    nub_record = await _create_record(
        db,
        id=980435,
        steamid64=player_id,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="18.500",
        teleports=4,
        points=120,
    )
    pro_record = await _create_record(
        db,
        id=980436,
        steamid64=player_id,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="20.500",
        teleports=0,
        points=140,
    )
    await _create_record(
        db,
        id=980437,
        steamid64=player_id,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=1,
        time="16.500",
        teleports=3,
        points=160,
    )
    for record, record_type, points in (
        (nub_record, RecordType.NUB, 777),
        (pro_record, RecordType.PRO, 888),
    ):
        record_pb = (
            await db.exec(
                select(RecordPb).where(
                    RecordPb.record_uuid == record.uuid,
                    RecordPb.scope == ModeScope.KZT,
                    RecordPb.type == record_type,
                )
            )
        ).one()
        record_pb.points = points
        db.add(record_pb)
    await db.commit()

    steam_id_response = await client.get(
        "/v0/records/top",
        params={
            "steam_id": "STEAM_1:0:999999999",
            "modes_list_string": "kz_timer",
            "stage": 0,
            "tickrate": 128,
            "has_teleports": "true",
            "limit": 9999,
        },
    )
    steamid64_response = await client.get(
        "/v0/records/top",
        params={
            "steamid64": player_id,
            "modes_list_string": "kz_timer",
            "stage": 0,
            "tickrate": 128,
            "has_teleports": "true",
            "limit": 9999,
        },
    )

    assert steam_id_response.status_code == 200
    assert steamid64_response.status_code == 200
    assert steam_id_response.json() == steamid64_response.json()
    payload = steam_id_response.json()
    assert [row["id"] for row in payload] == [980435]
    assert list(payload[0]) == [
        "id",
        "steamid64",
        "player_name",
        "steam_id",
        "server_id",
        "map_id",
        "stage",
        "mode",
        "tickrate",
        "time",
        "teleports",
        "created_on",
        "updated_on",
        "updated_by",
        "record_filter_id",
        "server_name",
        "map_name",
        "points",
        "replay_id",
    ]
    assert payload[0]["steamid64"] == str(player_id)
    assert payload[0]["steam_id"] == "STEAM_1:0:999999999"
    assert payload[0]["points"] == 777

    globalapi_points_response = await client.get(
        "/v0/records/top",
        params={
            "steam_id": "STEAM_1:0:999999999",
            "modes_list_string": "kz_timer",
            "stage": 0,
            "has_teleports": "true",
            "use_gokz_top_points": "false",
        },
    )
    assert globalapi_points_response.status_code == 200
    assert globalapi_points_response.json()[0]["points"] == 120

    stage_one_response = await client.get(
        "/v0/records/top",
        params={
            "steam_id": "STEAM_1:0:999999999",
            "modes_list_string": "kz_timer",
            "stage": 1,
            "has_teleports": "true",
        },
    )
    assert stage_one_response.status_code == 200
    assert [row["id"] for row in stage_one_response.json()] == [980437]

    pro_response = await client.get(
        "/v0/records/top",
        params={
            "steam_id": "STEAM_1:0:999999999",
            "modes_list_string": "kz_timer",
            "stage": 0,
            "has_teleports": "false",
        },
    )
    assert pro_response.status_code == 200
    assert [row["id"] for row in pro_response.json()] == [980436]


async def test_read_record_v0_top_rejects_malformed_steam_id(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/v0/records/top",
        params={"steam_id": "not-a-steam-id"},
    )

    assert response.status_code == 500


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
        f"{settings.API_V1_STR}/records",
        params={"map_id": 980200},
    )
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()["data"]] == [981000]

    listed_all = await client.get(
        f"{settings.API_V1_STR}/records",
        params={"map_id": 980200, "exclude_cheaters": "false"},
    )
    assert listed_all.status_code == 200
    assert [row["id"] for row in listed_all.json()["data"]] == [981001, 981000]
    listed_all_points = {row["id"]: row["points"] for row in listed_all.json()["data"]}
    assert listed_all_points[981001] == 0
    assert listed_all_points[981000] > 0

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
    pb_all_points = {row["id"]: row["points"] for row in pb_all.json()}
    assert pb_all_points[981001] == 0
    assert pb_all_points[981000] > 0

    detail = await client.get(
        f"{settings.API_V1_STR}/records/{listed_all.json()['data'][0]['uuid']}"
    )
    assert detail.status_code == 200
    assert detail.json()["points"] == 0


async def test_read_records_v1_supports_map_name_filter(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    player_id = random_steamid64()
    await _seed_record_dependencies(
        db,
        map_name="kz_records_by_name",
        players=[(player_id, "Map Name Runner")],
    )
    record = await _create_record(
        db,
        id=981010,
        steamid64=player_id,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="12.345",
        teleports=0,
    )

    response = await client.get(
        f"{settings.API_V1_STR}/records",
        params={"map_name": "kz_records_by_name"},
    )

    assert response.status_code == 200
    assert [row["id"] for row in response.json()["data"]] == [record.id]


async def test_read_pb_records_v1_supports_map_name_and_custom_id_identifier(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    player_id = random_steamid64()
    await _seed_record_dependencies(
        db,
        map_name="kz_pb_by_name",
        players=[(player_id, "Identifier Runner")],
    )
    await _create_player(
        db,
        steamid64=player_id,
        name="Identifier Runner",
        custom_id="identifier-runner",
    )
    record = await _create_record(
        db,
        id=981011,
        steamid64=player_id,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="11.111",
        teleports=0,
    )

    map_response = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params={"map_name": "kz_pb_by_name", "scope": "OVR"},
    )
    assert map_response.status_code == 200
    assert [row["id"] for row in map_response.json()] == [record.id]

    identifier_response = await client.get(
        f"{settings.API_V1_STR}/records/pb",
        params={"identifier": "identifier-runner", "scope": "OVR"},
    )
    assert identifier_response.status_code == 200
    assert [row["id"] for row in identifier_response.json()] == [record.id]


async def test_read_record_ranks_v1_returns_ordered_map_local_ranks(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    first_player = random_steamid64()
    second_player = random_steamid64()
    third_player = random_steamid64()
    await _seed_record_dependencies(
        db,
        players=[
            (first_player, "First"),
            (second_player, "Second"),
            (third_player, "Third"),
        ],
    )
    await _create_map(db, id=980201, name="kz_record_second_map", difficulty=5)

    map_one_first = await _create_record(
        db,
        id=981020,
        steamid64=first_player,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="20.000",
        teleports=1,
    )
    map_one_second = await _create_record(
        db,
        id=981021,
        steamid64=second_player,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="21.000",
        teleports=1,
    )
    map_two_first = await _create_record(
        db,
        id=981022,
        steamid64=third_player,
        server_id=980300,
        mode_id=200,
        map_id=980201,
        stage=0,
        time="19.000",
        teleports=1,
    )

    response = await client.get(
        f"{settings.API_V1_STR}/records/rank",
        params=[
            ("uuid_list", str(map_one_second.uuid)),
            ("uuid_list", str(map_two_first.uuid)),
            ("uuid_list", "0195d2cc-6209-7f5a-8cb6-9f0f6f0f6f0f"),
            ("scope", "OVR"),
            ("type", "NUB"),
        ],
    )

    assert response.status_code == 200
    assert response.json() == {
        "data": [
            {
                "record_uuid": str(map_one_second.uuid),
                "rank": 2,
                "total_count": 2,
            },
            {
                "record_uuid": str(map_two_first.uuid),
                "rank": 1,
                "total_count": 1,
            },
            {
                "record_uuid": "0195d2cc-6209-7f5a-8cb6-9f0f6f0f6f0f",
                "rank": None,
                "total_count": None,
            },
        ],
        "count": 3,
    }
    assert map_one_first.uuid != map_one_second.uuid


async def test_read_record_ranks_v1_respects_scope_type_and_excludes_cheaters(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    clean_player = random_steamid64()
    banned_player = random_steamid64()
    nkz_player = random_steamid64()
    await _seed_record_dependencies(
        db,
        players=[
            (clean_player, "Clean"),
            (banned_player, "Banned"),
            (nkz_player, "NKZ"),
        ],
    )

    banned_nub = await _create_record(
        db,
        id=981030,
        steamid64=banned_player,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="18.000",
        teleports=2,
    )
    clean_pro = await _create_record(
        db,
        id=981031,
        steamid64=clean_player,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="19.000",
        teleports=0,
    )
    nkz_nub = await _create_record(
        db,
        id=981032,
        steamid64=nkz_player,
        server_id=980300,
        mode_id=203,
        map_id=980200,
        stage=0,
        time="20.000",
        teleports=1,
    )
    await _create_ban(db, id=981130, steamid64=banned_player, expires_on=None)

    nub_response = await client.get(
        f"{settings.API_V1_STR}/records/rank",
        params=[
            ("uuid_list", str(clean_pro.uuid)),
            ("uuid_list", str(banned_nub.uuid)),
            ("scope", "OVR"),
            ("type", "NUB"),
        ],
    )
    assert nub_response.status_code == 200
    assert nub_response.json()["data"] == [
        {
            "record_uuid": str(clean_pro.uuid),
            "rank": 1,
            "total_count": 2,
        },
        {
            "record_uuid": str(banned_nub.uuid),
            "rank": None,
            "total_count": None,
        },
    ]

    pro_response = await client.get(
        f"{settings.API_V1_STR}/records/rank",
        params=[
            ("uuid_list", str(clean_pro.uuid)),
            ("uuid_list", str(nkz_nub.uuid)),
            ("scope", "OVR"),
            ("type", "PRO"),
        ],
    )
    assert pro_response.status_code == 200
    assert pro_response.json()["data"] == [
        {
            "record_uuid": str(clean_pro.uuid),
            "rank": 1,
            "total_count": 1,
        },
        {
            "record_uuid": str(nkz_nub.uuid),
            "rank": None,
            "total_count": None,
        },
    ]

    scope_response = await client.get(
        f"{settings.API_V1_STR}/records/rank",
        params=[
            ("uuid_list", str(nkz_nub.uuid)),
            ("scope", "KZT"),
            ("type", "NUB"),
        ],
    )
    assert scope_response.status_code == 200
    assert scope_response.json()["data"] == [
        {
            "record_uuid": str(nkz_nub.uuid),
            "rank": 2,
            "total_count": 2,
        },
    ]


async def test_read_record_ranks_v1_supports_country_filter(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    german_player = random_steamid64()
    french_player = random_steamid64()
    await _seed_record_dependencies(
        db,
        players=[
            (german_player, "German"),
            (french_player, "French"),
        ],
    )
    await _create_player(
        db,
        steamid64=german_player,
        name="German",
        country="DE",
    )
    await _create_player(
        db,
        steamid64=french_player,
        name="French",
        country="FR",
    )

    german_record = await _create_record(
        db,
        id=981040,
        steamid64=german_player,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="19.000",
        teleports=1,
    )
    await _create_record(
        db,
        id=981041,
        steamid64=french_player,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="18.000",
        teleports=1,
    )

    response = await client.get(
        f"{settings.API_V1_STR}/records/rank",
        params=[
            ("uuid_list", str(german_record.uuid)),
            ("scope", "OVR"),
            ("type", "NUB"),
            ("country", "DE"),
        ],
    )

    assert response.status_code == 200
    assert response.json()["data"] == [
        {
            "record_uuid": str(german_record.uuid),
            "rank": 1,
            "total_count": 1,
        },
    ]


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
    points_by_id = {row["id"]: row["points"] for row in response.json()["data"]}
    assert points_by_id[record.id] == 0

    filtered = await client.get(
        f"{settings.API_V1_STR}/records/recent",
        params={"points_more_or_equal_than": 1},
    )
    assert filtered.status_code == 200
    assert record.id not in [row["id"] for row in filtered.json()["data"]]


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
