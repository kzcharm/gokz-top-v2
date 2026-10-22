"""Operational backfills must honor dry runs and record durable progress."""

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app import backfill_player_session_geo as geo
from app import backfill_recent_wr_events as wr
from app import backfill_record_pb_updated_at as pb_dates
from app.models import (
    Map,
    MapCourse,
    Player,
    PlayerSession,
    ScheduledTaskState,
    ServerGroup,
)
from app.services.geoip import GeoIPLocation
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


def use_session(monkeypatch: pytest.MonkeyPatch, db: AsyncSession) -> None:
    @asynccontextmanager
    async def session_factory():
        yield db

    for module in (geo, wr, pb_dates):
        monkeypatch.setattr(module, "async_session_maker", session_factory)


async def test_geo_backfill_batches_and_dry_run(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_session(monkeypatch, db)
    steamid = random_steamid64()
    db.add(Player(steamid64=steamid, name="Geo backfill"))
    group = ServerGroup(
        name="Geo backfill group", custom_id="geo-backfill", api_key=str(uuid.uuid7())
    )
    db.add(group)
    await db.flush()
    now = datetime(2026, 1, 2, tzinfo=UTC)
    first = PlayerSession(
        id=uuid.uuid7(),
        player_steamid64=steamid,
        server_group_id=group.id,
        connected_at=now,
        last_heartbeat_at=now,
        ip_address="8.8.8.8",
        map_name="kz_geo",
    )
    second = PlayerSession(
        id=uuid.uuid7(),
        player_steamid64=steamid,
        server_group_id=group.id,
        connected_at=now - timedelta(seconds=1),
        last_heartbeat_at=now,
        ip_address="127.0.0.1",
        map_name="kz_geo",
    )
    db.add_all([first, second])
    await db.flush()
    lookups = []

    def lookup(address):
        lookups.append(address)
        return (
            GeoIPLocation(
                country_code="US", region_name="California", city_name="Mountain View"
            )
            if address == "8.8.8.8"
            else None
        )

    monkeypatch.setattr(geo, "lookup_geoip_city", lookup)
    await geo._main_async(["--dry-run"])
    assert not lookups and first.geo_country is None
    await geo._main_async(["--batch-size", "1"])
    await db.refresh(first)
    await db.refresh(second)
    assert (first.geo_country, first.geo_region, first.geo_city) == (
        "US",
        "California",
        "Mountain View",
    )
    assert second.geo_country is None
    assert lookups == ["8.8.8.8", "127.0.0.1"]
    with pytest.raises(ValueError, match="batch-size"):
        await geo._main_async(["--batch-size", "0"])
    await pb_dates._main_async(["--dry-run"])
    await pb_dates._main_async([])


async def test_recent_wr_backfill_dry_run_resume_reset_and_repair(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_session(monkeypatch, db)
    db.add(Map(id=972380, name="kz_wr_backfill_quality", validated=True))
    await db.flush()
    course = MapCourse(map_id=972380, stage=0)
    db.add(course)
    await db.flush()
    course_id = course.id
    await wr._main_async(["--dry-run"])
    state = await db.get(ScheduledTaskState, wr.RECENT_WR_BACKFILL_TASK_NAME)
    assert state.last_successful_at is None
    await wr._main_async(["--reset-progress", "--batch-size", "1"])
    await db.refresh(state)
    assert state.cursor == course_id
    assert state.last_processed == 1 and state.last_successful_at is not None
    await wr._main_async([])
    assert state.last_processed == 1
    await wr._main_async(["--course-id", str(course_id), "--dry-run"])
    await wr._main_async(["--course-id", str(course_id)])
    with pytest.raises(ValueError, match="validated main-map course"):
        await wr._main_async(["--course-id", "2147483647"])
    state = await db.get(ScheduledTaskState, wr.RECENT_WR_BACKFILL_TASK_NAME)
    assert "validated main-map course" in state.last_error
    assert state.last_errors == 1
    for args in (["--course-id", "0"], ["--dry-run", "--reset-progress"]):
        with pytest.raises(ValueError):
            await wr._main_async(args)
