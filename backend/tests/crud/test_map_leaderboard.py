from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlmodel import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.models import (
    Ban,
    BanType,
    Map,
    MapLeaderboardCache,
    MapReviewSummaryCache,
    ModeScope,
    Player,
    Record,
    RecordPatch,
    RecordFilter,
    ServerGlobalapi,
)
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


async def _create_player(db: AsyncSession, *, steamid64: int, name: str) -> None:
    db.add(Player(steamid64=steamid64, name=name))
    await db.flush()


async def _create_map(
    db: AsyncSession,
    *,
    map_id: int,
    name: str,
    difficulty: int,
    validated: bool = True,
) -> None:
    db.add(
        Map(
            id=map_id,
            name=name,
            filesize=1,
            validated=validated,
            difficulty=difficulty,
            approved_by_steamid64=0,
        )
    )
    await db.flush()


async def _create_server(db: AsyncSession, *, server_id: int) -> None:
    db.add(
        ServerGlobalapi(
            id=server_id,
            port=27015,
            ip="203.0.113.90",
            name="Map Leaderboard Server",
            owner_steamid64=0,
            approval_status=1,
            approved_by_steamid64=0,
        )
    )
    await db.flush()


async def _create_record_filter(
    db: AsyncSession,
    *,
    record_filter_id: int,
    map_id: int,
    mode_id: int,
    tier: int,
) -> None:
    db.add(
        RecordFilter(
            id=record_filter_id,
            map_id=map_id,
            stage=0,
            mode_id=mode_id,
            tickrate=128,
            has_teleports=False,
            tier=tier,
            updated_by_id="0",
        )
    )
    await db.flush()


async def _upsert_record(
    db: AsyncSession,
    *,
    record_id: int,
    steamid64: int,
    server_id: int,
    mode_id: int,
    map_id: int,
    stage: int,
    teleports: int,
    time_seconds: str,
    is_valid: bool = True,
) -> Record:
    record, _created, _updated = await crud.upsert_record(
        session=db,
        record_id=record_id,
        record_uuid=None,
        steamid64=steamid64,
        server_id=server_id,
        mode_id=mode_id,
        map_id=map_id,
        stage=stage,
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
    return record


async def _create_ban(
    db: AsyncSession,
    *,
    ban_id: int,
    steamid64: int,
    expires_on: datetime | None,
) -> None:
    db.add(
        Ban(
            id=ban_id,
            ban_type=BanType.BHOP_HACK,
            expires_on=expires_on,
            steamid64=steamid64,
            notes="cheater",
            stats="stats",
            server_id=1,
            updated_by_id="1",
            created_on=datetime(2099, 1, 2, tzinfo=UTC),
            updated_on=datetime(2099, 1, 2, tzinfo=UTC),
        )
    )
    await db.flush()


async def test_rebuild_map_leaderboards_aggregates_scope_metrics(
    db: AsyncSession,
) -> None:
    map_id = 2_130_000_001
    server_id = 2_130_000_002
    await _create_map(db, map_id=map_id, name="kz_map_lb_metrics", difficulty=4)
    await _create_server(db, server_id=server_id)

    player_alpha = random_steamid64()
    player_beta = random_steamid64()
    player_gamma = random_steamid64()
    player_banned = random_steamid64()
    player_invalid = random_steamid64()
    for steamid64, name in (
        (player_alpha, "Alpha"),
        (player_beta, "Beta"),
        (player_gamma, "Gamma"),
        (player_banned, "Banned"),
        (player_invalid, "Invalid"),
    ):
        await _create_player(db, steamid64=steamid64, name=name)

    await _upsert_record(
        db,
        record_id=2_130_100_001,
        steamid64=player_alpha,
        server_id=server_id,
        mode_id=200,
        map_id=map_id,
        stage=0,
        teleports=1,
        time_seconds="10.000",
    )
    await _upsert_record(
        db,
        record_id=2_130_100_002,
        steamid64=player_alpha,
        server_id=server_id,
        mode_id=200,
        map_id=map_id,
        stage=0,
        teleports=0,
        time_seconds="9.000",
    )
    await _upsert_record(
        db,
        record_id=2_130_100_003,
        steamid64=player_beta,
        server_id=server_id,
        mode_id=200,
        map_id=map_id,
        stage=0,
        teleports=1,
        time_seconds="20.000",
    )
    await _upsert_record(
        db,
        record_id=2_130_100_004,
        steamid64=player_gamma,
        server_id=server_id,
        mode_id=203,
        map_id=map_id,
        stage=0,
        teleports=1,
        time_seconds="30.000",
    )
    await _upsert_record(
        db,
        record_id=2_130_100_005,
        steamid64=player_gamma,
        server_id=server_id,
        mode_id=203,
        map_id=map_id,
        stage=0,
        teleports=1,
        time_seconds="31.000",
    )
    await _upsert_record(
        db,
        record_id=2_130_100_006,
        steamid64=player_banned,
        server_id=server_id,
        mode_id=200,
        map_id=map_id,
        stage=0,
        teleports=1,
        time_seconds="40.000",
    )
    await _upsert_record(
        db,
        record_id=2_130_100_007,
        steamid64=player_invalid,
        server_id=server_id,
        mode_id=200,
        map_id=map_id,
        stage=0,
        teleports=1,
        time_seconds="50.000",
        is_valid=False,
    )
    await _upsert_record(
        db,
        record_id=2_130_100_008,
        steamid64=player_beta,
        server_id=server_id,
        mode_id=200,
        map_id=map_id,
        stage=1,
        teleports=1,
        time_seconds="5.000",
    )
    await _create_ban(
        db,
        ban_id=2_130_200_001,
        steamid64=player_banned,
        expires_on=None,
    )
    await db.commit()

    await db.exec(delete(MapLeaderboardCache))
    await db.commit()

    rebuilt = await crud.rebuild_map_leaderboards(
        session=db,
        scopes=[ModeScope.KZT],
        map_ids=[map_id],
    )
    await db.commit()

    row = await db.get(MapLeaderboardCache, (map_id, ModeScope.KZT))
    assert rebuilt == 1
    assert row is not None
    assert row.total_finishes == 5
    assert row.total_playtime == pytest.approx(100.0)
    assert row.average_first_completion_time == pytest.approx(19.667)
    assert row.median_first_completion_time == pytest.approx(20.0)
    assert row.average_playtime_per_player == pytest.approx(33.333)
    assert row.median_playtime_per_player == pytest.approx(20.0)
    assert row.average_finishes_per_player == pytest.approx(1.67)
    assert row.median_finishes_per_player == pytest.approx(2.0)
    assert row.pro_nub_ratio == pytest.approx(0.3333)
    assert row.unique_pro_finishes == 1
    assert row.unique_nub_finishes == 3


async def test_rebuild_map_leaderboards_counts_nub_as_all_unique_finishers(
    db: AsyncSession,
) -> None:
    map_id = 2_130_500_001
    server_id = 2_130_500_002
    await _create_map(db, map_id=map_id, name="kz_map_lb_nub", difficulty=5)
    await _create_server(db, server_id=server_id)

    player_pro_only = random_steamid64()
    player_nub_only = random_steamid64()
    for steamid64, name in (
        (player_pro_only, "ProOnly"),
        (player_nub_only, "NubOnly"),
    ):
        await _create_player(db, steamid64=steamid64, name=name)

    await _upsert_record(
        db,
        record_id=2_130_510_001,
        steamid64=player_pro_only,
        server_id=server_id,
        mode_id=200,
        map_id=map_id,
        stage=0,
        teleports=0,
        time_seconds="10.000",
    )
    await _upsert_record(
        db,
        record_id=2_130_510_002,
        steamid64=player_nub_only,
        server_id=server_id,
        mode_id=200,
        map_id=map_id,
        stage=0,
        teleports=5,
        time_seconds="11.000",
    )
    await db.commit()

    await db.exec(delete(MapLeaderboardCache))
    await db.commit()

    await crud.rebuild_map_leaderboards(
        session=db,
        scopes=[ModeScope.KZT],
        map_ids=[map_id],
    )
    await db.commit()

    row = await db.get(MapLeaderboardCache, (map_id, ModeScope.KZT))
    assert row is not None
    assert row.unique_nub_finishes == 2
    assert row.unique_pro_finishes == 1
    assert row.unique_nub_finishes >= row.unique_pro_finishes


async def test_rebuild_map_leaderboards_interpolates_even_player_medians(
    db: AsyncSession,
) -> None:
    map_id = 2_130_600_001
    server_id = 2_130_600_002
    await _create_map(db, map_id=map_id, name="kz_map_lb_even", difficulty=5)
    await _create_server(db, server_id=server_id)

    players = [random_steamid64() for _ in range(4)]
    for index, steamid64 in enumerate(players, start=1):
        await _create_player(db, steamid64=steamid64, name=f"Even{index}")

    record_id = 2_130_610_000
    for finish_count, (steamid64, first_time) in enumerate(
        zip(players, ("10.000", "20.000", "30.000", "40.000"), strict=True),
        start=1,
    ):
        for offset in range(finish_count):
            await _upsert_record(
                db,
                record_id=record_id,
                steamid64=steamid64,
                server_id=server_id,
                mode_id=200,
                map_id=map_id,
                stage=0,
                teleports=1,
                time_seconds=str(Decimal(first_time) + Decimal(offset * 10)),
            )
            record_id += 1
    await db.commit()

    await crud.rebuild_map_leaderboards(
        session=db,
        scopes=[ModeScope.KZT],
        map_ids=[map_id],
    )
    await db.commit()

    row = await db.get(MapLeaderboardCache, (map_id, ModeScope.KZT))
    assert row is not None
    assert row.median_first_completion_time == pytest.approx(25.0)
    assert row.median_finishes_per_player == pytest.approx(2.5)
    assert row.median_playtime_per_player == pytest.approx(45.0)


async def test_read_map_leaderboard_includes_zero_rows_and_review_summaries(
    db: AsyncSession,
) -> None:
    map_active_id = 2_131_000_001
    map_empty_id = 2_131_000_002
    map_hidden_id = 2_131_000_003
    server_id = 2_131_000_010
    player_id = random_steamid64()

    await _create_player(db, steamid64=player_id, name="Reader")
    await _create_server(db, server_id=server_id)
    await _create_map(db, map_id=map_active_id, name="kz_active", difficulty=6)
    await _create_map(db, map_id=map_empty_id, name="kz_empty", difficulty=3)
    await _create_map(
        db,
        map_id=map_hidden_id,
        name="kz_hidden",
        difficulty=2,
        validated=False,
    )
    await _create_record_filter(
        db,
        record_filter_id=2_131_100_001,
        map_id=map_active_id,
        mode_id=200,
        tier=5,
    )
    await _upsert_record(
        db,
        record_id=2_131_200_001,
        steamid64=player_id,
        server_id=server_id,
        mode_id=200,
        map_id=map_active_id,
        stage=0,
        teleports=1,
        time_seconds="15.500",
    )
    db.add(
        MapReviewSummaryCache(
            map_id=map_active_id,
            overall_avg=4.5,
            gameplay_avg=4.0,
            visuals_avg=5.0,
            reviews_count=2,
            gameplay_count=2,
            visuals_count=1,
            comments_count=1,
            updated_at=datetime(2099, 1, 3, tzinfo=UTC),
        )
    )
    await db.commit()

    payload = await crud.read_map_leaderboard(session=db, scope=ModeScope.KZT)

    assert payload.count == 2
    assert [entry.map.name for entry in payload.data] == ["kz_active", "kz_empty"]

    active_entry = payload.data[0]
    assert active_entry.tier == 5
    assert active_entry.review_summary is not None
    assert active_entry.review_summary.comments_count == 1
    assert active_entry.total_finishes == 1
    assert active_entry.total_playtime == pytest.approx(15.5)
    assert active_entry.average_first_completion_time == pytest.approx(15.5)
    assert active_entry.median_first_completion_time == pytest.approx(15.5)
    assert active_entry.pro_nub_ratio == pytest.approx(0.0)
    assert active_entry.unique_nub_finishes == 1

    empty_entry = payload.data[1]
    assert empty_entry.tier == 3
    assert empty_entry.review_summary is None
    assert empty_entry.total_finishes == 0
    assert empty_entry.total_playtime == 0
    assert empty_entry.average_first_completion_time == 0
    assert empty_entry.median_first_completion_time == 0
    assert empty_entry.average_playtime_per_player == 0
    assert empty_entry.median_playtime_per_player == 0
    assert empty_entry.average_finishes_per_player == 0
    assert empty_entry.median_finishes_per_player == 0
    assert empty_entry.pro_nub_ratio == 0
    assert empty_entry.unique_pro_finishes == 0
    assert empty_entry.unique_nub_finishes == 0
    assert empty_entry.updated_at is None


async def test_upsert_record_rebuilds_old_and_new_map_leaderboard_keys(
    db: AsyncSession,
) -> None:
    map_alpha_id = 2_132_000_001
    map_beta_id = 2_132_000_002
    server_id = 2_132_000_010
    player_id = random_steamid64()

    await _create_player(db, steamid64=player_id, name="Mover")
    await _create_server(db, server_id=server_id)
    await _create_map(db, map_id=map_alpha_id, name="kz_alpha", difficulty=4)
    await _create_map(db, map_id=map_beta_id, name="kz_beta", difficulty=6)

    await _upsert_record(
        db,
        record_id=2_132_100_001,
        steamid64=player_id,
        server_id=server_id,
        mode_id=200,
        map_id=map_alpha_id,
        stage=0,
        teleports=1,
        time_seconds="12.000",
    )
    await db.commit()

    assert await db.get(MapLeaderboardCache, (map_alpha_id, ModeScope.OVR)) is not None
    assert await db.get(MapLeaderboardCache, (map_alpha_id, ModeScope.KZT)) is not None

    await crud.upsert_record(
        session=db,
        record_id=2_132_100_001,
        record_uuid=None,
        steamid64=player_id,
        server_id=server_id,
        mode_id=201,
        map_id=map_beta_id,
        stage=0,
        time_seconds=Decimal("13.000"),
        teleports=1,
        points=0,
        created_on=datetime(2099, 1, 1, tzinfo=UTC),
        updated_on=datetime(2099, 1, 2, tzinfo=UTC),
        updated_by=player_id,
        replay_id=None,
        is_valid=True,
    )
    await db.commit()

    assert await db.get(MapLeaderboardCache, (map_alpha_id, ModeScope.OVR)) is None
    assert await db.get(MapLeaderboardCache, (map_alpha_id, ModeScope.KZT)) is None

    beta_ovr = await db.get(MapLeaderboardCache, (map_beta_id, ModeScope.OVR))
    beta_skz = await db.get(MapLeaderboardCache, (map_beta_id, ModeScope.SKZ))
    assert beta_ovr is not None
    assert beta_ovr.total_finishes == 1
    assert beta_skz is not None
    assert beta_skz.total_finishes == 1


async def test_update_record_validity_refreshes_map_leaderboard_row(
    db: AsyncSession,
) -> None:
    map_id = 2_133_000_001
    server_id = 2_133_000_010
    player_id = random_steamid64()

    await _create_player(db, steamid64=player_id, name="Validity")
    await _create_server(db, server_id=server_id)
    await _create_map(db, map_id=map_id, name="kz_validity", difficulty=4)

    record = await _upsert_record(
        db,
        record_id=2_133_100_001,
        steamid64=player_id,
        server_id=server_id,
        mode_id=200,
        map_id=map_id,
        stage=0,
        teleports=1,
        time_seconds="11.000",
    )
    await db.commit()

    assert await db.get(MapLeaderboardCache, (map_id, ModeScope.KZT)) is not None

    await crud.update_record_validity(
        session=db,
        record=record,
        patch=RecordPatch(is_valid=False),
    )

    assert await db.get(MapLeaderboardCache, (map_id, ModeScope.KZT)) is None
