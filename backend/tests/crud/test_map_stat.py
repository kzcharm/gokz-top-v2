from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.models import (
    Ban,
    BanType,
    Map,
    MapStatCache,
    MapStatType,
    ModeScope,
    Player,
    RecordType,
    ServerGlobalapi,
    mode_scope_to_id,
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
            ip="203.0.113.92",
            name="Map Stats Server",
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
    mode_id: int,
    teleports: int,
    time_seconds: str,
    is_valid: bool = True,
) -> None:
    await crud.upsert_record(
        session=db,
        record_id=record_id,
        record_uuid=None,
        steamid64=steamid64,
        server_id=server_id,
        mode_id=mode_id,
        map_id=map_id,
        stage=0,
        time_seconds=Decimal(time_seconds),
        teleports=teleports,
        points=0,
        created_on=datetime(2099, 1, 1, tzinfo=UTC),
        updated_on=datetime(2099, 1, 1, tzinfo=UTC),
        updated_by=steamid64,
        replay_id=None,
        is_valid=is_valid,
    )
    await db.flush()


async def _create_ban(db: AsyncSession, *, steamid64: int, server_id: int) -> None:
    db.add(
        Ban(
            id=981_599_001,
            ban_type=BanType.BHOP_HACK,
            expires_on=datetime(2100, 1, 1, tzinfo=UTC),
            steamid64=steamid64,
            notes="active",
            stats="stats",
            server_id=server_id,
            updated_by_id="1",
            created_on=datetime(2099, 1, 2, tzinfo=UTC),
            updated_on=datetime(2099, 1, 2, tzinfo=UTC),
        )
    )
    await db.flush()


def _content(
    row: MapStatCache | None,
):
    assert row is not None
    return row.content


async def test_rebuild_map_stats_builds_nub_and_pro_distributions(
    db: AsyncSession,
) -> None:
    map_id = 981_500_001
    server_id = 981_500_002
    await _create_map(db, map_id=map_id, name="kz_map_stats")
    await _create_server(db, server_id=server_id)

    player_nub_wr = random_steamid64()
    player_nub_gap = random_steamid64()
    player_pro_wr = random_steamid64()
    player_pro_gap = random_steamid64()
    for steamid64, name in (
        (player_nub_wr, "Nub WR"),
        (player_nub_gap, "Nub Gap"),
        (player_pro_wr, "Pro WR"),
        (player_pro_gap, "Pro Gap"),
    ):
        await _create_player(db, steamid64=steamid64, name=name)

    await _create_record(
        db,
        record_id=981_501_001,
        steamid64=player_nub_wr,
        server_id=server_id,
        map_id=map_id,
        mode_id=200,
        teleports=1,
        time_seconds="10.000",
    )
    await _create_record(
        db,
        record_id=981_501_002,
        steamid64=player_nub_gap,
        server_id=server_id,
        map_id=map_id,
        mode_id=200,
        teleports=2,
        time_seconds="12.500",
    )
    await _create_record(
        db,
        record_id=981_501_003,
        steamid64=player_pro_wr,
        server_id=server_id,
        map_id=map_id,
        mode_id=200,
        teleports=0,
        time_seconds="9.000",
    )
    await _create_record(
        db,
        record_id=981_501_004,
        steamid64=player_pro_gap,
        server_id=server_id,
        map_id=map_id,
        mode_id=200,
        teleports=0,
        time_seconds="18.000",
    )

    rebuilt = await crud.rebuild_map_stats_for_keys(
        session=db,
        keys=[
            (map_id, mode_scope_to_id(ModeScope.KZT), RecordType.NUB),
            (map_id, mode_scope_to_id(ModeScope.KZT), RecordType.PRO),
        ],
    )
    await db.commit()

    assert rebuilt == 2

    nub_row = await db.get(
        MapStatCache,
        (map_id, ModeScope.KZT, RecordType.NUB, MapStatType.WR_GAP_DISTRIBUTION),
    )
    pro_row = await db.get(
        MapStatCache,
        (map_id, ModeScope.KZT, RecordType.PRO, MapStatType.WR_GAP_DISTRIBUTION),
    )
    nub_content = _content(nub_row)
    pro_content = _content(pro_row)

    assert nub_content["wr_time"] == 9.0
    assert nub_content["median_wr_gap"] == pytest.approx(-1.363, abs=0.001)
    assert nub_content["total_pb_count"] == 4
    assert nub_content["plotted_pb_count"] == 3
    assert [bin_row["label"] for bin_row in nub_content["bins"]] == [
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
    assert [bin_row["count"] for bin_row in nub_content["bins"]] == [1, 0, 0, 0, 1, 0, 0, 1, 0]
    assert nub_content["bins"][0]["lower_bound"] == -3.5
    assert nub_content["bins"][-1]["upper_bound"] == 1.0

    assert pro_content["wr_time"] == 9.0
    assert pro_content["median_wr_gap"] == 0.0
    assert pro_content["total_pb_count"] == 2
    assert pro_content["plotted_pb_count"] == 1
    assert [bin_row["label"] for bin_row in pro_content["bins"]] == ["0"]
    assert [bin_row["count"] for bin_row in pro_content["bins"]] == [1]


async def test_rebuild_map_stats_separates_scope_and_excludes_banned_invalid_rows(
    db: AsyncSession,
) -> None:
    map_id = 981_510_001
    server_id = 981_510_002
    await _create_map(db, map_id=map_id, name="kz_map_stats_scope")
    await _create_server(db, server_id=server_id)

    player_kzt = random_steamid64()
    player_nkz = random_steamid64()
    player_banned = random_steamid64()
    player_invalid = random_steamid64()
    for steamid64, name in (
        (player_kzt, "KZT"),
        (player_nkz, "NKZ"),
        (player_banned, "Banned"),
        (player_invalid, "Invalid"),
    ):
        await _create_player(db, steamid64=steamid64, name=name)

    await _create_record(
        db,
        record_id=981_511_001,
        steamid64=player_kzt,
        server_id=server_id,
        map_id=map_id,
        mode_id=200,
        teleports=1,
        time_seconds="10.000",
    )
    await _create_record(
        db,
        record_id=981_511_002,
        steamid64=player_nkz,
        server_id=server_id,
        map_id=map_id,
        mode_id=203,
        teleports=1,
        time_seconds="20.000",
    )
    await _create_record(
        db,
        record_id=981_511_003,
        steamid64=player_banned,
        server_id=server_id,
        map_id=map_id,
        mode_id=200,
        teleports=1,
        time_seconds="30.000",
    )
    await _create_ban(db, steamid64=player_banned, server_id=server_id)
    await _create_record(
        db,
        record_id=981_511_004,
        steamid64=player_invalid,
        server_id=server_id,
        map_id=map_id,
        mode_id=200,
        teleports=1,
        time_seconds="40.000",
        is_valid=False,
    )

    await crud.rebuild_map_stats_for_keys(
        session=db,
        keys=[
            (map_id, mode_scope_to_id(ModeScope.KZT), RecordType.NUB),
            (map_id, mode_scope_to_id(ModeScope.OVR), RecordType.NUB),
        ],
    )
    await db.commit()

    kzt_row = await db.get(
        MapStatCache,
        (map_id, ModeScope.KZT, RecordType.NUB, MapStatType.WR_GAP_DISTRIBUTION),
    )
    ovr_row = await db.get(
        MapStatCache,
        (map_id, ModeScope.OVR, RecordType.NUB, MapStatType.WR_GAP_DISTRIBUTION),
    )

    assert _content(kzt_row)["total_pb_count"] == 2
    assert _content(kzt_row)["plotted_pb_count"] == 1
    assert _content(ovr_row)["total_pb_count"] == 2
    assert _content(ovr_row)["plotted_pb_count"] == 1
    assert _content(ovr_row)["median_wr_gap"] == 0.0
    assert [bin_row["label"] for bin_row in _content(ovr_row)["bins"]] == ["0"]
    assert [bin_row["count"] for bin_row in _content(ovr_row)["bins"]] == [1]


async def test_get_or_rebuild_map_stats_builds_missing_cache_rows(
    db: AsyncSession,
) -> None:
    map_id = 981_520_001
    server_id = 981_520_002
    await _create_map(db, map_id=map_id, name="kz_map_stats_lazy")
    await _create_server(db, server_id=server_id)
    player = random_steamid64()
    await _create_player(db, steamid64=player, name="Lazy")
    await _create_record(
        db,
        record_id=981_521_001,
        steamid64=player,
        server_id=server_id,
        map_id=map_id,
        mode_id=200,
        teleports=1,
        time_seconds="12.000",
    )

    stats = await crud.get_or_rebuild_map_stats(
        session=db,
        map_id=map_id,
        scope=ModeScope.KZT,
    )

    nub_row = await db.get(
        MapStatCache,
        (map_id, ModeScope.KZT, RecordType.NUB, MapStatType.WR_GAP_DISTRIBUTION),
    )
    pro_row = await db.get(
        MapStatCache,
        (map_id, ModeScope.KZT, RecordType.PRO, MapStatType.WR_GAP_DISTRIBUTION),
    )
    assert stats.map_id == map_id
    assert stats.nub_wr_gap_distribution.total_pb_count == 1
    assert stats.nub_wr_gap_distribution.median_wr_gap is None
    assert stats.pro_wr_gap_distribution.total_pb_count == 0
    assert stats.pro_wr_gap_distribution.median_wr_gap is None
    assert nub_row is not None
    assert pro_row is not None
