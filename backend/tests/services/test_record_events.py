import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlmodel import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.models import (
    Map,
    MapCourse,
    MapCourseTier,
    ModeScope,
    Player,
    Record,
    ServerGlobalapi,
    legacy_mode_id_to_kz_mode,
)
from app.services import record_events
from app.services.record_events import (
    build_recent_record_snapshot_event,
    build_recent_record_upsert_event,
)
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


async def _create_player(
    db: AsyncSession,
    *,
    steamid64: int,
    name: str,
) -> None:
    await db.exec(delete(Player).where(Player.steamid64 == steamid64))
    await db.commit()
    db.add(Player(steamid64=steamid64, name=name))
    await db.commit()


async def _create_map(
    db: AsyncSession,
    *,
    map_id: int,
    name: str,
    difficulty: int,
) -> None:
    await db.exec(delete(Map).where(Map.id == map_id))
    await db.commit()
    db.add(
        Map(
            id=map_id,
            name=name,
            filesize=0,
            validated=True,
            difficulty=difficulty,
            approved_by_steamid64=0,
        )
    )
    await db.commit()


async def _create_course_tier(
    db: AsyncSession,
    *,
    map_id: int,
    mode_id: int,
    tier: int,
) -> None:
    course = MapCourse(map_id=map_id, stage=0)
    db.add(course)
    await db.flush()
    db.add(
        MapCourseTier(
            course_id=course.id,
            mode=legacy_mode_id_to_kz_mode(mode_id),
            tier=tier,
            updated_by_id="0",
        )
    )
    await db.commit()


async def _create_server(
    db: AsyncSession,
    *,
    server_id: int,
    name: str,
) -> None:
    await db.exec(delete(ServerGlobalapi).where(ServerGlobalapi.id == server_id))
    await db.commit()
    db.add(
        ServerGlobalapi(
            id=server_id,
            port=27015,
            ip="203.0.113.10",
            name=name,
            owner_steamid64=None,
            approval_status=1,
            approved_by_steamid64=None,
        )
    )
    await db.commit()


async def _create_record(
    db: AsyncSession,
    *,
    record_id: int | None,
    steamid64: int,
    map_id: int,
    server_id: int,
    mode_id: int,
    created_on: datetime,
) -> Record:
    if record_id is not None:
        await db.exec(delete(Record).where(Record.id == record_id))
        await db.commit()

    record = Record(
        id=record_id,
        steamid64=steamid64,
        server_id=server_id,
        mode_id=mode_id,
        map_id=map_id,
        stage=0,
        time=Decimal("12.345"),
        teleports=0,
        points=420,
        created_on=created_on,
        updated_on=created_on,
        updated_by=steamid64,
        is_valid=True,
    )
    db.add(record)
    await db.commit()
    await crud.rebuild_record_pbs(session=db)
    await db.commit()
    await db.refresh(record)
    return record


async def test_build_recent_record_snapshot_event_returns_latest_records(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @asynccontextmanager
    async def _session_maker():
        yield db

    monkeypatch.setattr(record_events, "async_session_maker", _session_maker)
    await db.exec(delete(Record))
    await db.commit()

    player_one = random_steamid64()
    player_two = random_steamid64()
    await _create_player(db, steamid64=player_one, name="Snapshot One")
    await _create_player(db, steamid64=player_two, name="Snapshot Two")
    await _create_map(db, map_id=990200, name="kz_snapshot", difficulty=5)
    await _create_course_tier(db, map_id=990200, mode_id=200, tier=5)
    await _create_server(db, server_id=990300, name="Snapshot Server")

    oldest = await _create_record(
        db,
        record_id=990400,
        steamid64=player_one,
        map_id=990200,
        server_id=990300,
        mode_id=200,
        created_on=datetime(2026, 3, 30, 12, 0, tzinfo=UTC),
    )
    newest = await _create_record(
        db,
        record_id=990401,
        steamid64=player_two,
        map_id=990200,
        server_id=990300,
        mode_id=201,
        created_on=datetime(2026, 3, 30, 12, 1, tzinfo=UTC),
    )

    event = await build_recent_record_snapshot_event()

    assert event.type == "record.snapshot"
    assert [record.uuid for record in event.records] == [newest.uuid, oldest.uuid]
    assert event.records[0].map.tier == 5
    assert event.records[0].mode.name == "SKZ"

    skz_event = await build_recent_record_snapshot_event(scope=ModeScope.SKZ)
    assert [record.uuid for record in skz_event.records] == [newest.uuid]


async def test_build_recent_record_upsert_event_returns_single_record_payload(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @asynccontextmanager
    async def _session_maker():
        yield db

    monkeypatch.setattr(record_events, "async_session_maker", _session_maker)

    steamid64 = random_steamid64()
    await _create_player(db, steamid64=steamid64, name="Realtime Runner")
    await _create_map(db, map_id=991200, name="kz_realtime", difficulty=3)
    await _create_server(db, server_id=991300, name="Realtime Server")
    record = await _create_record(
        db,
        record_id=None,
        steamid64=steamid64,
        map_id=991200,
        server_id=991300,
        mode_id=200,
        created_on=datetime(2026, 3, 30, 12, 2, tzinfo=UTC),
    )

    event = await build_recent_record_upsert_event(str(record.uuid))

    assert event is not None
    assert event.type == "record.upserted"
    assert event.record.uuid == record.uuid
    assert event.record.player.display_name == "Realtime Runner"
    assert event.record.server.name == "Realtime Server"
    assert event.record.mode.name == "KZT"
    assert await build_recent_record_upsert_event(
        str(record.uuid),
        scope=ModeScope.SKZ,
    ) is None


async def test_build_recent_record_upsert_event_rejects_invalid_or_missing_record() -> (
    None
):
    assert await build_recent_record_upsert_event("not-a-uuid") is None
    assert await build_recent_record_upsert_event(str(uuid.uuid4())) is None
