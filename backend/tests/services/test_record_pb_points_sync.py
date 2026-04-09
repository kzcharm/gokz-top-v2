import random
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.models import Map, Player, RecordType, ScheduledTaskState, ServerGlobalapi
from app.services import record_pb_points_task
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


async def _create_player(db: AsyncSession, *, steamid64: int, name: str) -> None:
    db.add(Player(steamid64=steamid64, name=name))
    await db.commit()


async def _create_map(db: AsyncSession, *, map_id: int, name: str) -> None:
    db.add(
        Map(
            id=map_id,
            name=name,
            filesize=1,
            validated=True,
            difficulty=4,
            approved_by_steamid64=0,
        )
    )
    await db.commit()


async def _create_server(db: AsyncSession, *, server_id: int, name: str) -> None:
    db.add(
        ServerGlobalapi(
            id=server_id,
            port=27015,
            ip="203.0.113.50",
            name=name,
            owner_steamid64=0,
            approval_status=1,
            approved_by_steamid64=0,
        )
    )
    await db.commit()


async def _upsert_record(
    db: AsyncSession,
    *,
    record_id: int,
    steamid64: int,
    server_id: int,
    map_id: int,
    stage: int,
    teleports: int,
    created_on: datetime,
) -> None:
    await crud.upsert_record(
        session=db,
        record_id=record_id,
        record_uuid=None,
        steamid64=steamid64,
        server_id=server_id,
        mode_id=200,
        map_id=map_id,
        stage=stage,
        time_seconds=Decimal("10.000") + Decimal(record_id % 10),
        teleports=teleports,
        points=0,
        created_on=created_on,
        updated_on=created_on,
        updated_by=steamid64,
        replay_id=None,
        is_valid=True,
    )
    await db.commit()


async def test_rebuild_changed_record_pb_points_dedupes_recent_buckets(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2099, 4, 4, 12, 0, tzinfo=UTC)
    id_base = random.randint(2_000_000_000, 2_100_000_000)
    map_id = id_base
    server_id = id_base + 1
    record_id_base = id_base + 2

    await _create_map(db, map_id=map_id, name="kz_recent_bucket")
    await _create_server(db, server_id=server_id, name="Recent Bucket Server")

    first_player = random_steamid64()
    second_player = random_steamid64()
    third_player = random_steamid64()
    await _create_player(db, steamid64=first_player, name="Recent One")
    await _create_player(db, steamid64=second_player, name="Recent Two")
    await _create_player(db, steamid64=third_player, name="Recent Three")

    await _upsert_record(
        db,
        record_id=record_id_base,
        steamid64=first_player,
        server_id=server_id,
        map_id=map_id,
        stage=0,
        teleports=1,
        created_on=datetime(2099, 4, 4, 11, 0, tzinfo=UTC),
    )
    await _upsert_record(
        db,
        record_id=record_id_base + 1,
        steamid64=second_player,
        server_id=server_id,
        map_id=map_id,
        stage=0,
        teleports=1,
        created_on=datetime(2099, 4, 4, 11, 5, tzinfo=UTC),
    )
    await _upsert_record(
        db,
        record_id=record_id_base + 2,
        steamid64=third_player,
        server_id=server_id,
        map_id=map_id,
        stage=0,
        teleports=0,
        created_on=datetime(2099, 4, 4, 11, 10, tzinfo=UTC),
    )

    state = await db.get(ScheduledTaskState, record_pb_points_task.TASK_NAME)
    if state is None:
        db.add(
            ScheduledTaskState(
                task_name=record_pb_points_task.TASK_NAME,
                last_successful_at=datetime(2099, 4, 4, 10, 30, tzinfo=UTC),
            )
        )
    else:
        state.last_successful_at = datetime(2099, 4, 4, 10, 30, tzinfo=UTC)
        db.add(state)
    await db.commit()

    calls: list[tuple[int, int, RecordType]] = []

    async def _fake_rebuild_bucket(
        *,
        session: AsyncSession,
        course_id: int,
        scope_id: int,
        record_type: RecordType,
    ) -> int:
        del session
        calls.append((course_id, scope_id, record_type))
        return 1

    monkeypatch.setattr(record_pb_points_task, "get_datetime_utc", lambda: now)
    monkeypatch.setattr(
        record_pb_points_task.crud,
        "rebuild_record_pb_points_bucket",
        _fake_rebuild_bucket,
    )

    result = await record_pb_points_task.rebuild_changed_record_pb_points(session=db)

    assert result.processed == 4
    assert result.updated == 4
    assert len(calls) == 4
    assert {call[1] for call in calls} == {0, 1}
    assert {call[2] for call in calls} == {RecordType.NUB, RecordType.PRO}


async def test_rebuild_changed_record_pb_points_uses_24h_window_on_first_run(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2099, 4, 4, 12, 0, tzinfo=UTC)
    id_base = random.randint(2_100_000_000, 2_140_000_000)
    map_id = id_base
    server_id = id_base + 1
    record_id_base = id_base + 2

    await _create_map(db, map_id=map_id, name="kz_first_run_window")
    await _create_server(db, server_id=server_id, name="First Run Server")

    recent_player = random_steamid64()
    stale_player = random_steamid64()
    await _create_player(db, steamid64=recent_player, name="Window Recent")
    await _create_player(db, steamid64=stale_player, name="Window Stale")

    await _upsert_record(
        db,
        record_id=record_id_base,
        steamid64=recent_player,
        server_id=server_id,
        map_id=map_id,
        stage=0,
        teleports=1,
        created_on=datetime(2099, 4, 3, 13, 0, tzinfo=UTC),
    )
    await _upsert_record(
        db,
        record_id=record_id_base + 1,
        steamid64=stale_player,
        server_id=server_id,
        map_id=map_id,
        stage=1,
        teleports=1,
        created_on=datetime(2099, 4, 3, 11, 0, tzinfo=UTC),
    )

    calls: list[tuple[int, int, RecordType]] = []

    async def _fake_rebuild_bucket(
        *,
        session: AsyncSession,
        course_id: int,
        scope_id: int,
        record_type: RecordType,
    ) -> int:
        del session
        calls.append((course_id, scope_id, record_type))
        return 1

    monkeypatch.setattr(record_pb_points_task, "get_datetime_utc", lambda: now)
    monkeypatch.setattr(
        record_pb_points_task.crud,
        "rebuild_record_pb_points_bucket",
        _fake_rebuild_bucket,
    )

    result = await record_pb_points_task.rebuild_changed_record_pb_points(session=db)

    assert result.processed == 2
    assert len(calls) == 2
    assert {call[1] for call in calls} == {0, 1}
    assert {call[2] for call in calls} == {RecordType.NUB}
