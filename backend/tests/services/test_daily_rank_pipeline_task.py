from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.models import (
    Map,
    ModeScopeId,
    Player,
    Record,
    RecordPb,
    RecordType,
    ScheduledTaskState,
    ServerGlobalapi,
)
from app.services import daily_rank_pipeline_task
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


def _patch_session_maker(
    *,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @asynccontextmanager
    async def _session_maker() -> AsyncGenerator[AsyncSession]:
        yield db

    monkeypatch.setattr(daily_rank_pipeline_task, "async_session_maker", _session_maker)


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


async def test_load_daily_rank_selection_uses_previous_utc_day_window(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2099, 4, 4, 0, 5, tzinfo=UTC)
    map_id = 2_000_001
    server_id = 2_000_002
    record_id_base = 2_000_003

    await _create_map(db, map_id=map_id, name="kz_daily_window")
    await _create_server(db, server_id=server_id, name="Daily Window Server")

    lower_bound_player = random_steamid64()
    middle_player = random_steamid64()
    upper_bound_player = random_steamid64()
    await _create_player(db, steamid64=lower_bound_player, name="Lower Bound")
    await _create_player(db, steamid64=middle_player, name="Middle")
    await _create_player(db, steamid64=upper_bound_player, name="Upper Bound")

    await _upsert_record(
        db,
        record_id=record_id_base,
        steamid64=lower_bound_player,
        server_id=server_id,
        map_id=map_id,
        stage=0,
        teleports=1,
        created_on=datetime(2099, 4, 3, 0, 0, tzinfo=UTC),
    )
    await _upsert_record(
        db,
        record_id=record_id_base + 1,
        steamid64=middle_player,
        server_id=server_id,
        map_id=map_id,
        stage=1,
        teleports=0,
        created_on=datetime(2099, 4, 3, 12, 0, tzinfo=UTC),
    )
    await _upsert_record(
        db,
        record_id=record_id_base + 2,
        steamid64=upper_bound_player,
        server_id=server_id,
        map_id=map_id,
        stage=2,
        teleports=1,
        created_on=datetime(2099, 4, 4, 0, 0, tzinfo=UTC),
    )

    record_rows = (await db.exec(select(Record))).all()
    record_pbs = (await db.exec(select(RecordPb))).all()
    assert len(record_rows) == 3
    assert len(record_pbs) == 8
    record_pbs_by_steamid64 = {
        steamid64: [record_pb for record_pb in record_pbs if record_pb.steamid64 == steamid64]
        for steamid64 in (lower_bound_player, middle_player, upper_bound_player)
    }
    records_by_steamid64 = {record.steamid64: record for record in record_rows}

    # Selection must follow the linked record creation time, not record_pb.updated_at.
    for record_pb in record_pbs_by_steamid64[lower_bound_player]:
        record_pb.updated_at = datetime(2099, 4, 4, 6, 0, tzinfo=UTC)
        db.add(record_pb)
    for record_pb in record_pbs_by_steamid64[middle_player]:
        record_pb.updated_at = datetime(2099, 4, 2, 23, 59, tzinfo=UTC)
        db.add(record_pb)
    for record_pb in record_pbs_by_steamid64[upper_bound_player]:
        record_pb.updated_at = datetime(2099, 4, 3, 18, 0, tzinfo=UTC)
        db.add(record_pb)
    await db.commit()

    monkeypatch.setattr(daily_rank_pipeline_task, "get_datetime_utc", lambda: now)

    selection = await daily_rank_pipeline_task.load_daily_rank_selection(session=db)

    assert selection.window_start == datetime(2099, 4, 3, 0, 0, tzinfo=UTC)
    assert selection.window_end == datetime(2099, 4, 4, 0, 0, tzinfo=UTC)
    assert selection.pb_row_count == 6
    lower_course_id = record_pbs_by_steamid64[lower_bound_player][0].course_id
    middle_course_id = record_pbs_by_steamid64[middle_player][0].course_id
    assert selection.point_buckets == [
        (lower_course_id, int(ModeScopeId.OVR), RecordType.NUB),
        (lower_course_id, int(ModeScopeId.KZT), RecordType.NUB),
        (middle_course_id, int(ModeScopeId.OVR), RecordType.NUB),
        (middle_course_id, int(ModeScopeId.OVR), RecordType.PRO),
        (middle_course_id, int(ModeScopeId.KZT), RecordType.NUB),
        (middle_course_id, int(ModeScopeId.KZT), RecordType.PRO),
    ]
    assert selection.leaderboard_keys == sorted(
        [
            (int(ModeScopeId.OVR), lower_bound_player),
            (int(ModeScopeId.KZT), lower_bound_player),
            (int(ModeScopeId.OVR), middle_player),
            (int(ModeScopeId.KZT), middle_player),
        ]
    )
    assert selection.map_leaderboard_keys == [
        (map_id, 0),
        (map_id, 1),
    ]
    assert selection.steamid64s == sorted([lower_bound_player, middle_player])
    assert records_by_steamid64[lower_bound_player].created_at == datetime(
        2099, 4, 3, 0, 0, tzinfo=UTC
    )
    assert records_by_steamid64[middle_player].created_at == datetime(
        2099, 4, 3, 12, 0, tzinfo=UTC
    )
    assert records_by_steamid64[upper_bound_player].created_at == datetime(
        2099, 4, 4, 0, 0, tzinfo=UTC
    )


async def test_load_daily_rank_selection_ignores_record_pb_updated_at_window_mismatch(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2099, 4, 4, 0, 5, tzinfo=UTC)
    map_id = 2_000_101
    server_id = 2_000_102
    record_id_base = 2_000_103

    await _create_map(db, map_id=map_id, name="kz_daily_window_mismatch")
    await _create_server(db, server_id=server_id, name="Daily Window Mismatch Server")

    excluded_player = random_steamid64()
    included_player = random_steamid64()
    await _create_player(db, steamid64=excluded_player, name="Excluded By Record Time")
    await _create_player(db, steamid64=included_player, name="Included By Record Time")

    await _upsert_record(
        db,
        record_id=record_id_base,
        steamid64=excluded_player,
        server_id=server_id,
        map_id=map_id,
        stage=0,
        teleports=1,
        created_on=datetime(2099, 4, 2, 23, 59, tzinfo=UTC),
    )
    await _upsert_record(
        db,
        record_id=record_id_base + 1,
        steamid64=included_player,
        server_id=server_id,
        map_id=map_id,
        stage=1,
        teleports=0,
        created_on=datetime(2099, 4, 3, 13, 0, tzinfo=UTC),
    )

    record_pbs = (await db.exec(select(RecordPb))).all()
    assert len(record_pbs) == 6
    record_pbs_by_steamid64 = {
        steamid64: [record_pb for record_pb in record_pbs if record_pb.steamid64 == steamid64]
        for steamid64 in (excluded_player, included_player)
    }
    for record_pb in record_pbs_by_steamid64[excluded_player]:
        record_pb.updated_at = datetime(2099, 4, 3, 8, 0, tzinfo=UTC)
        db.add(record_pb)
    for record_pb in record_pbs_by_steamid64[included_player]:
        record_pb.updated_at = datetime(2099, 4, 2, 22, 0, tzinfo=UTC)
        db.add(record_pb)
    await db.commit()

    monkeypatch.setattr(daily_rank_pipeline_task, "get_datetime_utc", lambda: now)

    selection = await daily_rank_pipeline_task.load_daily_rank_selection(session=db)

    assert selection.window_start == datetime(2099, 4, 3, 0, 0, tzinfo=UTC)
    assert selection.window_end == datetime(2099, 4, 4, 0, 0, tzinfo=UTC)
    assert selection.pb_row_count == 4
    included_course_id = record_pbs_by_steamid64[included_player][0].course_id
    assert selection.point_buckets == [
        (included_course_id, int(ModeScopeId.OVR), RecordType.NUB),
        (included_course_id, int(ModeScopeId.OVR), RecordType.PRO),
        (included_course_id, int(ModeScopeId.KZT), RecordType.NUB),
        (included_course_id, int(ModeScopeId.KZT), RecordType.PRO),
    ]
    assert selection.leaderboard_keys == [
        (int(ModeScopeId.OVR), included_player),
        (int(ModeScopeId.KZT), included_player),
    ]
    assert selection.map_leaderboard_keys == []
    assert selection.steamid64s == [included_player]


async def test_run_daily_rank_pipeline_runs_steps_in_sequence(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_session_maker(db=db, monkeypatch=monkeypatch)
    selection = daily_rank_pipeline_task.DailyRankSelection(
        window_start=datetime(2099, 4, 3, 0, 0, tzinfo=UTC),
        window_end=datetime(2099, 4, 4, 0, 0, tzinfo=UTC),
        pb_row_count=3,
        point_buckets=[(1, 2, RecordType.NUB)],
        leaderboard_keys=[(2, 76561198000000001)],
        map_leaderboard_keys=[(123, 0), (123, 1)],
        steamid64s=[76561198000000001],
    )
    order: list[str] = []

    async def _load_selection(
        *,
        session: AsyncSession,
    ) -> daily_rank_pipeline_task.DailyRankSelection:
        del session
        order.append("select")
        return selection

    async def _rebuild_points(
        *,
        session: AsyncSession,
        selection: daily_rank_pipeline_task.DailyRankSelection,
    ) -> int:
        del session, selection
        order.append("points")
        return 5

    async def _rebuild_leaderboard(
        *,
        session: AsyncSession,
        selection: daily_rank_pipeline_task.DailyRankSelection,
    ) -> tuple[int, int]:
        del session, selection
        order.append("leaderboard")
        return (2, 7)

    async def _rebuild_map_leaderboards(
        *,
        session: AsyncSession,
        selection: daily_rank_pipeline_task.DailyRankSelection,
    ) -> int:
        del session
        assert selection.map_leaderboard_keys == [(123, 0), (123, 1)]
        order.append("maps")
        return 2

    async def _refresh_profiles(
        *,
        session: AsyncSession,
        steamid64s: list[int],
    ) -> daily_rank_pipeline_task.SteamRefreshResult:
        del session
        assert steamid64s == selection.steamid64s
        order.append("steam")
        return daily_rank_pipeline_task.SteamRefreshResult(
            processed=1,
            created=1,
            updated=3,
            skipped=0,
        )

    monkeypatch.setattr(
        daily_rank_pipeline_task, "load_daily_rank_selection", _load_selection
    )
    monkeypatch.setattr(
        daily_rank_pipeline_task, "rebuild_daily_rank_points", _rebuild_points
    )
    monkeypatch.setattr(
        daily_rank_pipeline_task,
        "rebuild_daily_rank_leaderboards",
        _rebuild_leaderboard,
    )
    monkeypatch.setattr(
        daily_rank_pipeline_task,
        "rebuild_daily_rank_map_leaderboards",
        _rebuild_map_leaderboards,
    )
    monkeypatch.setattr(
        daily_rank_pipeline_task,
        "refresh_daily_rank_player_profiles",
        _refresh_profiles,
    )

    result = await daily_rank_pipeline_task.run_daily_rank_pipeline_task(
        only_stale=False
    )

    assert order == ["select", "points", "leaderboard", "maps", "steam"]
    assert result is not None
    assert result.processed == 3
    assert result.created == 3
    assert result.updated == 17
    assert result.warnings == 0


async def test_run_daily_rank_pipeline_aborts_on_first_failure(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_session_maker(db=db, monkeypatch=monkeypatch)
    now = datetime(2099, 4, 4, 0, 5, tzinfo=UTC)
    selection = daily_rank_pipeline_task.DailyRankSelection(
        window_start=datetime(2099, 4, 3, 0, 0, tzinfo=UTC),
        window_end=datetime(2099, 4, 4, 0, 0, tzinfo=UTC),
        pb_row_count=1,
        point_buckets=[(1, 2, RecordType.NUB)],
        leaderboard_keys=[(2, 76561198000000001)],
        map_leaderboard_keys=[(123, 0)],
        steamid64s=[76561198000000001],
    )
    order: list[str] = []

    async def _load_selection(
        *,
        session: AsyncSession,
    ) -> daily_rank_pipeline_task.DailyRankSelection:
        del session
        order.append("select")
        return selection

    async def _rebuild_points(
        *,
        session: AsyncSession,
        selection: daily_rank_pipeline_task.DailyRankSelection,
    ) -> int:
        del session, selection
        order.append("points")
        raise RuntimeError("points failed")

    async def _rebuild_leaderboard(
        *,
        session: AsyncSession,
        selection: daily_rank_pipeline_task.DailyRankSelection,
    ) -> tuple[int, int]:
        del session, selection
        order.append("leaderboard")
        return (0, 0)

    monkeypatch.setattr(daily_rank_pipeline_task, "get_datetime_utc", lambda: now)
    monkeypatch.setattr(
        daily_rank_pipeline_task, "load_daily_rank_selection", _load_selection
    )
    monkeypatch.setattr(
        daily_rank_pipeline_task, "rebuild_daily_rank_points", _rebuild_points
    )
    monkeypatch.setattr(
        daily_rank_pipeline_task,
        "rebuild_daily_rank_leaderboards",
        _rebuild_leaderboard,
    )

    result = await daily_rank_pipeline_task.run_daily_rank_pipeline_task(
        only_stale=False
    )

    assert result is None
    assert order == ["select", "points"]
    state = await db.get(ScheduledTaskState, daily_rank_pipeline_task.TASK_NAME)
    assert state is not None
    assert state.last_successful_at is None
    assert state.last_error == "points failed"


async def test_run_daily_rank_pipeline_skips_after_success_for_current_day(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_session_maker(db=db, monkeypatch=monkeypatch)
    now = datetime(2099, 4, 4, 12, 0, tzinfo=UTC)
    db.add(
        ScheduledTaskState(
            task_name=daily_rank_pipeline_task.TASK_NAME,
            last_successful_at=datetime(2099, 4, 4, 0, 0, tzinfo=UTC),
        )
    )
    await db.commit()

    monkeypatch.setattr(daily_rank_pipeline_task, "get_datetime_utc", lambda: now)

    result = await daily_rank_pipeline_task.run_daily_rank_pipeline_task(
        only_stale=True
    )

    assert result is None
