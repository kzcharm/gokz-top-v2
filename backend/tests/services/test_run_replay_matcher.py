from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.models import Map, Player, Record, RecordPb, ServerGlobalapi
from app.services.run_replay_matcher import match_record_for_run_replay
from app.services.run_replay_parser import parse_run_replay_bytes
from tests.utils.run_replay import build_synthetic_run_replay

pytestmark = pytest.mark.asyncio


async def _create_player(db: AsyncSession, *, steamid64: int, name: str) -> None:
    await db.exec(delete(Player).where(Player.steamid64 == steamid64))
    await db.commit()
    db.add(Player(steamid64=steamid64, name=name))
    await db.commit()


async def _create_map(db: AsyncSession, *, id: int, name: str) -> None:
    await db.exec(delete(Map).where(Map.id == id))
    await db.commit()
    db.add(
        Map(
            id=id,
            name=name,
            filesize=1,
            validated=True,
            difficulty=4,
            approved_by_steamid64=76561198003275951,
        )
    )
    await db.commit()


async def _create_server(db: AsyncSession, *, id: int, name: str) -> None:
    await db.exec(delete(ServerGlobalapi).where(ServerGlobalapi.id == id))
    await db.commit()
    for steamid64 in (76561198000000010, 76561198000000020):

        if await db.get(Player, steamid64) is None:

            db.add(Player(steamid64=steamid64, name=str(steamid64)))

    db.add(

        ServerGlobalapi(
            id=id,
            port=27015,
            ip=f"203.0.113.{id % 255}",
            name=name,
            owner_steamid64=76561198000000010,
            approval_status=1,
            approved_by_steamid64=76561198000000020,
        )
    )
    await db.commit()


async def _create_record(
    db: AsyncSession,
    *,
    id: int,
    steamid64: int,
    map_id: int,
    mode_id: int,
    stage: int,
    time_seconds: Decimal,
    created_on: datetime,
) -> Record:
    record_uuid_subquery = select(Record.uuid).where(Record.id == id)
    await db.exec(delete(RecordPb).where(RecordPb.record_uuid.in_(record_uuid_subquery)))
    await db.exec(delete(Record).where(Record.id == id))
    await db.commit()
    record, _created, _updated = await crud.upsert_record(
        session=db,
        record_id=id,
        record_uuid=None,
        steamid64=steamid64,
        server_id=986000,
        mode_id=mode_id,
        map_id=map_id,
        stage=stage,
        time_seconds=time_seconds,
        teleports=0,
        points=0,
        created_on=created_on,
        updated_on=created_on,
        updated_by=steamid64,
        replay_id=None,
        is_valid=True,
    )
    await db.commit()
    await db.refresh(record)
    return record


async def _seed_dependencies(
    db: AsyncSession,
    *,
    steamid64: int,
    map_id: int = 985000,
    map_name: str = "kz_match_map",
) -> None:
    await _create_player(db, steamid64=steamid64, name="Match Runner")
    await _create_map(db, id=map_id, name=map_name)
    await _create_server(db, id=986000, name="Match Server")


async def test_match_record_for_run_replay_returns_exact_match(db: AsyncSession) -> None:
    synthetic = build_synthetic_run_replay(map_name="kz_match_map", course=1)
    replay = parse_run_replay_bytes(
        data=synthetic.replay_bytes,
        source_name="match.replay",
    )
    await _seed_dependencies(db, steamid64=synthetic.steamid64)
    record = await _create_record(
        db,
        id=987000,
        steamid64=synthetic.steamid64,
        map_id=985000,
        mode_id=200,
        stage=1,
        time_seconds=replay.time,
        created_on=replay.recorded_at + timedelta(hours=1),
    )

    result = await match_record_for_run_replay(session=db, replay=replay)

    assert result.is_ambiguous is False
    assert result.match is not None
    assert result.match.record.uuid == record.uuid


async def test_match_record_for_run_replay_rejects_timestamp_outside_window(
    db: AsyncSession,
) -> None:
    synthetic = build_synthetic_run_replay(map_name="kz_time_window")
    replay = parse_run_replay_bytes(
        data=synthetic.replay_bytes,
        source_name="window.replay",
    )
    await _seed_dependencies(
        db,
        steamid64=synthetic.steamid64,
        map_name="kz_time_window",
    )
    await _create_record(
        db,
        id=987001,
        steamid64=synthetic.steamid64,
        map_id=985000,
        mode_id=200,
        stage=0,
        time_seconds=replay.time,
        created_on=replay.recorded_at + timedelta(hours=25),
    )

    result = await match_record_for_run_replay(session=db, replay=replay)

    assert result.match is None
    assert result.is_ambiguous is False
    assert result.candidates == ()


async def test_match_record_for_run_replay_prefers_closest_created_at(
    db: AsyncSession,
) -> None:
    synthetic = build_synthetic_run_replay(map_name="kz_closest_map")
    replay = parse_run_replay_bytes(
        data=synthetic.replay_bytes,
        source_name="closest.replay",
    )
    await _seed_dependencies(
        db,
        steamid64=synthetic.steamid64,
        map_name="kz_closest_map",
    )
    farther = await _create_record(
        db,
        id=987002,
        steamid64=synthetic.steamid64,
        map_id=985000,
        mode_id=200,
        stage=0,
        time_seconds=replay.time,
        created_on=replay.recorded_at + timedelta(hours=3),
    )
    closer = await _create_record(
        db,
        id=987003,
        steamid64=synthetic.steamid64,
        map_id=985000,
        mode_id=200,
        stage=0,
        time_seconds=replay.time,
        created_on=replay.recorded_at + timedelta(minutes=30),
    )

    result = await match_record_for_run_replay(session=db, replay=replay)

    assert result.match is not None
    assert result.match.record.uuid == closer.uuid
    assert result.match.record.uuid != farther.uuid


async def test_match_record_for_run_replay_reports_equal_distance_as_ambiguous(
    db: AsyncSession,
) -> None:
    synthetic = build_synthetic_run_replay(map_name="kz_ambiguous_map")
    replay = parse_run_replay_bytes(
        data=synthetic.replay_bytes,
        source_name="ambiguous.replay",
    )
    await _seed_dependencies(
        db,
        steamid64=synthetic.steamid64,
        map_name="kz_ambiguous_map",
    )
    await _create_record(
        db,
        id=987004,
        steamid64=synthetic.steamid64,
        map_id=985000,
        mode_id=200,
        stage=0,
        time_seconds=replay.time,
        created_on=replay.recorded_at - timedelta(hours=2),
    )
    await _create_record(
        db,
        id=987005,
        steamid64=synthetic.steamid64,
        map_id=985000,
        mode_id=200,
        stage=0,
        time_seconds=replay.time,
        created_on=replay.recorded_at + timedelta(hours=2),
    )

    result = await match_record_for_run_replay(session=db, replay=replay)

    assert result.match is None
    assert result.is_ambiguous is True
    assert len(result.candidates) == 2
