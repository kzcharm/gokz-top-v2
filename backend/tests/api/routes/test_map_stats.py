from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.models import (
    Map,
    MapStatCache,
    MapStatType,
    ModeScope,
    Player,
    RecordType,
    ServerGlobalapi,
)
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


async def _create_player(db: AsyncSession, *, steamid64: int, name: str) -> None:
    db.add(Player(steamid64=steamid64, name=name))
    await db.flush()


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
    await db.flush()


async def _create_server(db: AsyncSession, *, server_id: int) -> None:
    db.add(
        ServerGlobalapi(
            id=server_id,
            port=27015,
            ip="203.0.113.93",
            name="Map Stats API Server",
            owner_steamid64=None,
            approval_status=1,
            approved_by_steamid64=None,
        )
    )
    await db.flush()


async def _create_record(
    db: AsyncSession,
    *,
    record_id: int,
    steamid64: int,
    server_id: int,
    map_id: int,
    teleports: int,
    time_seconds: str,
) -> None:
    await crud.upsert_record(
        session=db,
        record_id=record_id,
        record_uuid=None,
        steamid64=steamid64,
        server_id=server_id,
        mode_id=200,
        map_id=map_id,
        stage=0,
        time_seconds=Decimal(time_seconds),
        teleports=teleports,
        points=0,
        created_on=datetime(2099, 1, 1, tzinfo=UTC),
        updated_on=datetime(2099, 1, 1, tzinfo=UTC),
        updated_by=steamid64,
        replay_id=None,
        is_valid=True,
    )
    await db.flush()


async def test_read_map_stats_builds_cache_and_returns_nub_and_pro(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    map_id = 981_600_001
    server_id = 981_600_002
    await _create_map(db, map_id=map_id, name="kz_api_map_stats")
    await _create_server(db, server_id=server_id)

    nub_wr = random_steamid64()
    nub_gap = random_steamid64()
    pro_wr = random_steamid64()
    pro_gap = random_steamid64()
    for steamid64, name in (
        (nub_wr, "Nub WR"),
        (nub_gap, "Nub Gap"),
        (pro_wr, "Pro WR"),
        (pro_gap, "Pro Gap"),
    ):
        await _create_player(db, steamid64=steamid64, name=name)

    await _create_record(
        db,
        record_id=981_601_001,
        steamid64=nub_wr,
        server_id=server_id,
        map_id=map_id,
        teleports=1,
        time_seconds="10.000",
    )
    await _create_record(
        db,
        record_id=981_601_002,
        steamid64=nub_gap,
        server_id=server_id,
        map_id=map_id,
        teleports=2,
        time_seconds="12.500",
    )
    await _create_record(
        db,
        record_id=981_601_003,
        steamid64=pro_wr,
        server_id=server_id,
        map_id=map_id,
        teleports=0,
        time_seconds="9.000",
    )
    await _create_record(
        db,
        record_id=981_601_004,
        steamid64=pro_gap,
        server_id=server_id,
        map_id=map_id,
        teleports=0,
        time_seconds="18.000",
    )
    await db.commit()

    response = await client.get(
        f"{settings.API_V1_STR}/maps/{map_id}/stats",
        params={"scope": "KZT"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["map_id"] == map_id
    assert payload["scope"] == "KZT"
    assert payload["nub_wr_gap_distribution"]["wr_time"] == 9.0
    assert payload["nub_wr_gap_distribution"]["median_wr_gap"] == pytest.approx(
        -1.363,
        abs=0.001,
    )
    assert payload["nub_wr_gap_distribution"]["total_pb_count"] == 4
    assert payload["pro_wr_gap_distribution"]["wr_time"] == 9.0
    assert payload["pro_wr_gap_distribution"]["median_wr_gap"] == 0.0
    assert payload["pro_wr_gap_distribution"]["total_pb_count"] == 2
    assert [bin_row["label"] for bin_row in payload["nub_wr_gap_distribution"]["bins"]] == [
        "-3.5",
        "-3",
        "-2.5",
        "-2",
        "-1.5",
        "-1",
        "-0.5",
        "0",
        "0.5",
    ]
    assert [bin_row["count"] for bin_row in payload["nub_wr_gap_distribution"]["bins"]] == [
        1,
        0,
        0,
        0,
        1,
        0,
        0,
        1,
        0,
    ]
    assert [bin_row["label"] for bin_row in payload["pro_wr_gap_distribution"]["bins"]] == ["0"]
    assert [bin_row["count"] for bin_row in payload["pro_wr_gap_distribution"]["bins"]] == [1]

    nub_row = await db.get(
        MapStatCache,
        (map_id, ModeScope.KZT, RecordType.NUB, MapStatType.WR_GAP_DISTRIBUTION),
    )
    pro_row = await db.get(
        MapStatCache,
        (map_id, ModeScope.KZT, RecordType.PRO, MapStatType.WR_GAP_DISTRIBUTION),
    )
    assert nub_row is not None
    assert pro_row is not None


async def test_read_map_stats_returns_not_found_for_missing_map(
    client: AsyncClient,
) -> None:
    response = await client.get(
        f"{settings.API_V1_STR}/maps/999999999/stats",
        params={"scope": "KZT"},
    )

    assert response.status_code == 404
