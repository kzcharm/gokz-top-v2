"""History reads must remain eligible for the existing valid-record indexes."""

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlmodel import select

from app import crud
from app.crud import ban
from app.crud.record import get_pb_record_publics
from app.models import (
    Ban,
    BanType,
    KZMode,
    ModeScope,
    Player,
    RecentRecordListQuery,
    Record,
    RecordPb,
    RecordType,
    generate_uuid7,
)
from app.services.record_ingestion import accept_record
from tests.services.test_record_ingestion import setup_finish


@pytest.mark.asyncio
@pytest.mark.parametrize("record_type", [RecordType.NUB, RecordType.PRO])
@pytest.mark.parametrize("exclude_cheaters", [True, False])
async def test_pb_points_and_order_respect_ban_expiry(
    db, monkeypatch, record_type, exclude_cheaters
):
    group, _, payload = await setup_finish(db, KZMode.KZT)
    players = [payload.steamid64 + index for index in range(5)]
    db.add_all(Player(steamid64=player, name="PB ban fixture") for player in players)
    await db.flush()
    for index, player in enumerate(players):
        await accept_record(
            db,
            group,
            payload.model_copy(
                update={
                    "steamid64": player,
                    "record_uuid": generate_uuid7(),
                    "time": payload.time + index,
                }
            ),
            f"pb-ban-{index}",
        )
    now = (await db.execute(text("SELECT CURRENT_TIMESTAMP"))).scalar_one()
    expirations = [None, now + timedelta(seconds=1), now - timedelta(seconds=1), now]
    db.add_all(
        Ban(steamid64=player, ban_type=BanType.OTHER, expires_at=expires_at)
        for player, expires_at in zip(players[1:], expirations, strict=True)
    )
    for pb in (await db.exec(select(RecordPb))).all():
        index = players.index(pb.steamid64)
        pb.points = 100 + index
        pb.raw_rating_contribution = 1000 + index
        db.add(pb)
    await db.flush()
    monkeypatch.setattr(ban, "get_datetime_utc", lambda: now)

    for sort_by in ("time", "points", "raw_rating_contribution"):
        expected = [0, 3] if exclude_cheaters else [0, 1, 2, 3, 4]
        if sort_by != "time":
            expected = [3, 0] if exclude_cheaters else [3, 0, 1, 2, 4]
        for offset, limit in ((0, 100), (1, 2)):
            rows = await get_pb_record_publics(
                db,
                map_id=982345,
                map_name=None,
                stage=0,
                steamid64=None,
                scope=ModeScope.OVR,
                record_type=record_type,
                exclude_cheaters=exclude_cheaters,
                sort_by=sort_by,
                offset=offset,
                limit=limit,
                include_ranks=True,
            )
            assert [int(row.player.steamid64) for row in rows] == [
                players[index] for index in expected[offset : offset + limit]
            ]
            for row in rows:
                index = players.index(int(row.player.steamid64))
                active_ban = index in (1, 2, 4)
                assert row.points == (0 if active_ban else 100 + index)
                assert row.raw_rating_contribution == (
                    0 if active_ban else 1000 + index
                )
                assert (row.rank is None) == active_ban, (index, sort_by, offset)


@pytest.mark.asyncio
@pytest.mark.parametrize("record_type", [RecordType.NUB, RecordType.PRO])
async def test_pb_reads_include_native_metadata_without_extra_queries(
    db, monkeypatch, record_type
):
    group, server, payload = await setup_finish(db, KZMode.KZT)
    await accept_record(db, group, payload, "pb-query-count")
    queries = 0
    original = db.exec

    async def counted(*args, **kwargs):
        nonlocal queries
        queries += 1
        return await original(*args, **kwargs)

    monkeypatch.setattr(db, "exec", counted)
    records = await get_pb_record_publics(
        db,
        map_id=982345,
        map_name=None,
        stage=0,
        steamid64=None,
        scope=ModeScope.OVR,
        record_type=record_type,
    )
    assert len(records) == 1
    assert records[0].native_server_id == server.id
    assert records[0].native_server_name == records[0].server_name == "Test Server"
    assert records[0].points == 1000
    assert queries == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("history", ["map", "player", "recent"])
async def test_history_reads_can_use_partial_indexes(db, monkeypatch, history):
    group, server, payload = await setup_finish(db, KZMode.KZT)
    await accept_record(db, group, payload, "read-query-plan")
    db.add_all(
        [
            Record(
                steamid64=payload.steamid64,
                native_server_id=server.id,
                map_id=982345,
                stage=1,
                mode=KZMode.KZT,
                time=Decimal("1000"),
                teleports=1,
            )
            for _ in range(500)
        ]
    )
    await db.flush()
    await db.execute(text("ANALYZE record"))
    # Check index eligibility independently of the tiny fixture's cost estimates.
    await db.execute(text("SET LOCAL enable_seqscan = off"))
    original = db.exec
    plans = []
    calls = 0

    async def inspected(statement, *args, **kwargs):
        nonlocal calls
        calls += 1
        sql = str(
            statement.compile(
                dialect=db.get_bind().dialect, compile_kwargs={"literal_binds": True}
            )
        )
        if "record.is_valid" in sql and (
            "FROM record " in sql or "FROM record\n" in sql
        ):
            plans.append(
                (await db.execute(text("EXPLAIN (FORMAT JSON) " + sql))).scalar_one()[
                    0
                ]["Plan"]
            )
        return await original(statement, *args, **kwargs)

    monkeypatch.setattr(db, "exec", inspected)
    if history == "map":
        result = await crud.read_map_wr_history(
            session=db, map_id=982345, scope=ModeScope.OVR, record_type=RecordType.NUB
        )
        assert result.count == 1
        assert result.data[0].native_server_id == server.id
        assert result.data[0].server_name == "Test Server"
        assert calls == 1
    elif history == "player":
        result = await crud.read_record_run_history(
            session=db,
            steamid64=payload.steamid64,
            map_id=982345,
            stage=0,
            scope=ModeScope.OVR,
            record_type=RecordType.NUB,
        )
        assert result.count == 1
    else:
        records, count = await crud.read_recent_records(
            session=db,
            query=RecentRecordListQuery(
                steamid64=str(payload.steamid64), map_id=982345, stage=0
            ),
        )
        assert count == len(records) == 1

    def record_scans(node):
        return ([node] if node.get("Relation Name") == "record" else []) + [
            scan for child in node.get("Plans", []) for scan in record_scans(child)
        ]

    scans = [scan for plan in plans for scan in record_scans(plan)]
    assert scans
    assert any(
        scan.get("Index Name", "").startswith(
            ("ix_record_valid_", "ix_pb_map_", "ix_pb_player_")
        )
        for scan in scans
    ), scans
    assert all(
        scan.get("Index Name", "").startswith(
            ("ix_record_valid_", "ix_pb_map_", "ix_pb_player_", "record_pkey")
        )
        for scan in scans
    ), scans
