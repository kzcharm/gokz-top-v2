import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.models import (
    Jumpstat,
    JumpstatType,
    KZMode,
    Map,
    MapCourse,
    MapCourseTier,
    Player,
    Record,
    RecordFilter,
    RecordPb,
    ServerGlobalapi,
    legacy_mode_id_to_kz_mode,
)
from app.services.jump_replay_storage import save_jump_replay
from app.services.run_replay_storage import save_run_replay
from tests.utils.run_replay import build_synthetic_run_replay
from tests.utils.server import create_server_group as create_test_server_group
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


async def _create_player(
    db: AsyncSession,
    *,
    steamid64: int,
    name: str,
) -> Player:
    await db.exec(delete(Player).where(Player.steamid64 == steamid64))
    await db.commit()
    player = Player(steamid64=steamid64, name=name)
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
        tickrate=128,
        has_teleports=False,
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
    created_on: datetime | None = None,
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
        points=0,
        created_on=created_on or datetime(2026, 1, 1, tzinfo=UTC),
        updated_on=created_on or datetime(2026, 1, 1, tzinfo=UTC),
        updated_by=steamid64,
        replay_id=None,
        is_valid=True,
    )
    await db.commit()
    await db.refresh(record)
    return record


async def _create_jumpstat(
    db: AsyncSession,
    *,
    player_steamid64: int,
    server_group_id: uuid.UUID,
) -> Jumpstat:
    jumpstat = Jumpstat(
        player_steamid64=player_steamid64,
        server_group_id=server_group_id,
        type=JumpstatType.LJ,
        mode=KZMode.KZT,
        distance=Decimal("281.8030"),
        block=280,
        strafes=9,
        sync_percent=83,
        pre_speed=Decimal("276.1000"),
        max_speed=Decimal("366.7200"),
        w_count=0,
        overlap_count=0,
        dead_air_count=0,
        width=Decimal("33.8000"),
        height=Decimal("55.8000"),
        airtime_percent=100,
        offset=Decimal("0.0000"),
        crouched_ticks=21,
        edge=None,
        deviation=None,
        strafe_stats=[
            {
                "index": index,
                "sync_percent": min(100, 80 + index),
                "gain": float(12 + index),
                "loss": 0.0,
                "airtime_percent": 10 + index,
                "width": float(20 + index),
                "overlap_count": 0,
                "dead_air_count": 0,
            }
            for index in range(1, 10)
        ],
        jumped_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        created_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
    )
    db.add(jumpstat)
    await db.commit()
    await db.refresh(jumpstat)
    return jumpstat


def _mode_to_index(mode: KZMode) -> int:
    return {
        KZMode.VNL: 0,
        KZMode.SKZ: 1,
        KZMode.KZT: 2,
        KZMode.NKZ: 3,
    }[mode]


def _save_synthetic_run_replay(
    *,
    record: Record,
    map_name: str,
    steamid64: int,
    mode: KZMode,
) -> None:
    steam_account_id = steamid64 - 76561197960265728
    if steam_account_id <= 0 or steam_account_id > 2_147_483_647:
        raise ValueError(f"Unsupported synthetic replay steamid64: {steamid64}")
    synthetic = build_synthetic_run_replay(
        map_name=map_name,
        steam_account_id=steam_account_id,
        mode_index=_mode_to_index(mode),
        time_seconds=float(record.time),
        course=record.stage,
        teleports_used=record.teleports,
    )
    save_run_replay(
        map_name=map_name,
        replay_id=record.uuid,
        replay_bytes=synthetic.replay_bytes,
    )


async def test_read_run_replay_returns_404_for_unknown_record(
    client: AsyncClient,
) -> None:
    response = await client.get(
        f"{settings.API_V1_STR}/replays/00000000-0000-0000-0000-000000000000"
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Record not found"}


async def test_read_run_replay_returns_404_when_file_is_missing(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(settings, "REPLAY_STORAGE_DIR", tmp_path)
    player = await _create_player(db, steamid64=random_steamid64(), name="Runner")
    await _create_map(db, id=980200, name="kz_missing_run_replay")
    await _create_server_globalapi(db, id=980300, name="Replay Server")
    record = await _create_record(
        db,
        id=980400,
        steamid64=player.steamid64,
        server_id=980300,
        mode_id=200,
        map_id=980200,
        stage=0,
        time="35.000",
        teleports=0,
    )

    response = await client.get(f"{settings.API_V1_STR}/replays/{record.uuid}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Replay not found"}


async def test_read_run_replay_returns_replay_bytes(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(settings, "REPLAY_STORAGE_DIR", tmp_path)
    player = await _create_player(db, steamid64=random_steamid64(), name="Runner")
    await _create_map(db, id=980201, name="kz_has_run_replay")
    await _create_server_globalapi(db, id=980301, name="Replay Server")
    record = await _create_record(
        db,
        id=980401,
        steamid64=player.steamid64,
        server_id=980301,
        mode_id=200,
        map_id=980201,
        stage=0,
        time="34.000",
        teleports=0,
    )
    save_run_replay(
        map_name="kz_has_run_replay",
        replay_id=record.uuid,
        replay_bytes=b"run-replay",
    )

    response = await client.get(f"{settings.API_V1_STR}/replays/{record.uuid}")

    assert response.status_code == 200
    assert response.content == b"run-replay"
    assert "attachment" in response.headers["content-disposition"]
    assert f"{record.uuid}.replay" in response.headers["content-disposition"]


async def test_read_replays_returns_only_replay_backed_records_and_respects_filters(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(settings, "REPLAY_STORAGE_DIR", tmp_path)
    matching_player = await _create_player(
        db,
        steamid64=76561198012345678,
        name="Replay Runner",
    )
    other_player = await _create_player(
        db,
        steamid64=76561198012345679,
        name="Other Runner",
    )
    await _create_map(db, id=980210, name="kz_replay_filter_map", difficulty=6)
    await _create_map(db, id=980211, name="kz_other_map", difficulty=3)
    await _create_server_globalapi(db, id=980310, name="Replay Server")
    await _create_record_filter(db, id=981710, map_id=980210, stage=0, mode_id=201, tier=2)

    slower_record = await _create_record(
        db,
        id=980410,
        steamid64=matching_player.steamid64,
        server_id=980310,
        mode_id=201,
        map_id=980210,
        stage=0,
        time="31.000",
        teleports=0,
        created_on=datetime(2026, 1, 4, tzinfo=UTC),
    )
    faster_record = await _create_record(
        db,
        id=980409,
        steamid64=matching_player.steamid64,
        server_id=980310,
        mode_id=201,
        map_id=980210,
        stage=0,
        time="29.000",
        teleports=0,
        created_on=datetime(2026, 1, 5, tzinfo=UTC),
    )
    non_replay_record = await _create_record(
        db,
        id=980411,
        steamid64=matching_player.steamid64,
        server_id=980310,
        mode_id=201,
        map_id=980210,
        stage=0,
        time="32.000",
        teleports=0,
        created_on=datetime(2026, 1, 3, tzinfo=UTC),
    )
    other_replay_record = await _create_record(
        db,
        id=980412,
        steamid64=other_player.steamid64,
        server_id=980310,
        mode_id=201,
        map_id=980211,
        stage=0,
        time="30.000",
        teleports=0,
        created_on=datetime(2026, 1, 4, tzinfo=UTC),
    )
    bonus_record = await _create_record(
        db,
        id=980413,
        steamid64=matching_player.steamid64,
        server_id=980310,
        mode_id=201,
        map_id=980210,
        stage=1,
        time="20.000",
        teleports=0,
        created_on=datetime(2026, 1, 1, tzinfo=UTC),
    )
    _save_synthetic_run_replay(
        record=slower_record,
        map_name="kz_replay_filter_map",
        steamid64=matching_player.steamid64,
        mode=KZMode.SKZ,
    )
    _save_synthetic_run_replay(
        record=faster_record,
        map_name="kz_replay_filter_map",
        steamid64=matching_player.steamid64,
        mode=KZMode.SKZ,
    )
    _save_synthetic_run_replay(
        record=other_replay_record,
        map_name="kz_other_map",
        steamid64=other_player.steamid64,
        mode=KZMode.SKZ,
    )
    _save_synthetic_run_replay(
        record=bonus_record,
        map_name="kz_replay_filter_map",
        steamid64=matching_player.steamid64,
        mode=KZMode.SKZ,
    )

    response = await client.get(
        f"{settings.API_V1_STR}/replays",
        params={
            "steamid64": matching_player.steamid64,
            "map_name": "kz_replay_filter_map",
            "mode": "SKZ",
            "teleports": 0,
            "scope": "SKZ",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert [row["uuid"] for row in payload["data"]] == [
        str(faster_record.uuid),
        str(slower_record.uuid),
    ]
    assert str(non_replay_record.uuid) not in [row["uuid"] for row in payload["data"]]
    assert payload["data"][0]["player"]["steamid64"] == str(matching_player.steamid64)
    assert payload["data"][0]["map_name"] == "kz_replay_filter_map"
    assert payload["data"][0]["mode"] == "SKZ"
    assert payload["data"][0]["map_tier"] == 2

    fallback_scope_response = await client.get(
        f"{settings.API_V1_STR}/replays",
        params={
            "steamid64": matching_player.steamid64,
            "map_name": "kz_replay_filter_map",
            "mode": "SKZ",
            "teleports": 0,
            "scope": "KZT",
        },
    )

    assert fallback_scope_response.status_code == 200
    assert fallback_scope_response.json()["data"][0]["map_tier"] == 0
    assert str(bonus_record.uuid) not in [
        row["uuid"] for row in fallback_scope_response.json()["data"]
    ]


async def test_read_replays_without_map_name_scans_all_replay_folders(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(settings, "REPLAY_STORAGE_DIR", tmp_path)
    player = await _create_player(db, steamid64=76561198012345680, name="Global Runner")
    await _create_map(db, id=980220, name="kz_global_one")
    await _create_map(db, id=980221, name="kz_global_two")
    await _create_server_globalapi(db, id=980320, name="Replay Server")
    first_record = await _create_record(
        db,
        id=980420,
        steamid64=player.steamid64,
        server_id=980320,
        mode_id=200,
        map_id=980220,
        stage=0,
        time="15.000",
        teleports=0,
    )
    second_record = await _create_record(
        db,
        id=980421,
        steamid64=player.steamid64,
        server_id=980320,
        mode_id=200,
        map_id=980221,
        stage=0,
        time="25.000",
        teleports=0,
    )
    _save_synthetic_run_replay(
        record=first_record,
        map_name="kz_global_one",
        steamid64=player.steamid64,
        mode=KZMode.KZT,
    )
    _save_synthetic_run_replay(
        record=second_record,
        map_name="kz_global_two",
        steamid64=player.steamid64,
        mode=KZMode.KZT,
    )

    response = await client.get(
        f"{settings.API_V1_STR}/replays",
        params={"mode": "KZT"},
    )

    assert response.status_code == 200
    assert [row["uuid"] for row in response.json()["data"]][:2] == [
        str(first_record.uuid),
        str(second_record.uuid),
    ]


async def test_read_jump_replay_returns_404_for_unknown_jumpstat(
    client: AsyncClient,
) -> None:
    response = await client.get(
        f"{settings.API_V1_STR}/replays/jump/00000000-0000-0000-0000-000000000000"
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Jumpstat not found"}


async def test_read_jump_replay_returns_404_when_file_is_missing(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(settings, "REPLAY_STORAGE_DIR", tmp_path)
    group, _api_key = await create_test_server_group(db, name="Jump Group")
    player = await _create_player(db, steamid64=random_steamid64(), name="Jump Runner")
    jumpstat = await _create_jumpstat(
        db,
        player_steamid64=player.steamid64,
        server_group_id=group.id,
    )

    response = await client.get(f"{settings.API_V1_STR}/replays/jump/{jumpstat.id}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Jump replay not found"}


async def test_read_jump_replay_returns_replay_bytes(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(settings, "REPLAY_STORAGE_DIR", tmp_path)
    group, _api_key = await create_test_server_group(db, name="Jump Group")
    player = await _create_player(db, steamid64=random_steamid64(), name="Jump Runner")
    jumpstat = await _create_jumpstat(
        db,
        player_steamid64=player.steamid64,
        server_group_id=group.id,
    )
    save_jump_replay(jumpstat_id=jumpstat.id, replay_bytes=b"jump-replay")

    response = await client.get(f"{settings.API_V1_STR}/replays/jump/{jumpstat.id}")

    assert response.status_code == 200
    assert response.content == b"jump-replay"
    assert "attachment" in response.headers["content-disposition"]
    assert f"{jumpstat.id}.replay" in response.headers["content-disposition"]
