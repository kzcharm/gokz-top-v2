"""Record write refreshes must remain eligible for the partial course indexes."""

from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlmodel import select

from app.crud.map_leaderboard import _build_map_leaderboard_values_for_scope
from app.crud.record import _load_bucket_winner_entries
from app.models import KZMode, MapCourse, ModeScope, Record, RecordType
from app.services.record_ingestion import accept_record
from tests.services.test_record_ingestion import setup_finish


@pytest.mark.asyncio
async def test_write_refresh_plans_can_use_partial_course_indexes(db, monkeypatch):
    group, server, payload = await setup_finish(db, KZMode.KZT)
    await accept_record(db, group, payload, "write-query-plan")
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
    # Test eligibility for these indexes even on the small fixture database.
    await db.execute(text("SET LOCAL enable_seqscan = off"))
    course = (
        await db.exec(
            select(MapCourse).where(MapCourse.map_id == 982345, MapCourse.stage == 0)
        )
    ).one()
    original = db.exec
    plans = []

    async def inspected(statement, *args, **kwargs):
        sql = str(
            statement.compile(
                dialect=db.get_bind().dialect, compile_kwargs={"literal_binds": True}
            )
        )
        if "FROM record" in sql:
            plan = (
                await db.execute(text("EXPLAIN (FORMAT JSON) " + sql))
            ).scalar_one()[0]["Plan"]
            plans.append(plan)
        return await original(statement, *args, **kwargs)

    monkeypatch.setattr(db, "exec", inspected)
    winners = await _load_bucket_winner_entries(
        session=db,
        course_id=course.id,
        scope_id=ModeScope.OVR.scope_id,
        record_type=RecordType.NUB,
    )
    stats = await _build_map_leaderboard_values_for_scope(
        session=db, scope=ModeScope.OVR, map_ids=[982345]
    )
    assert len(winners) == 1 and winners[0][1].record_uuid == payload.record_uuid
    assert stats[0]["total_finishes"] == 1

    def record_scans(node):
        return ([node] if node.get("Relation Name") == "record" else []) + [
            scan for child in node.get("Plans", []) for scan in record_scans(child)
        ]

    scans = [scan for plan in plans for scan in record_scans(plan)]
    assert len(scans) >= 3
    assert all(
        scan.get("Index Name", "").startswith(("ix_record_valid_", "ix_pb_map_"))
        for scan in scans
    )
