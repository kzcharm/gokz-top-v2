from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.crud.leaderboard_player import _build_leaderboard_values
from app.models import (
    Ban,
    BanType,
    LeaderboardPlayer,
    Map,
    MapCourse,
    Player,
    RecordFilter,
    ServerGlobalapi,
)
from app.models.record import RecordScopeId
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
) -> int:
    db.add(
        Map(
            id=map_id,
            name=name,
            filesize=1,
            validated=True,
            difficulty=difficulty,
            approved_by_steamid64=0,
        )
    )
    await db.flush()
    course = MapCourse(map_id=map_id, stage=0)
    db.add(course)
    await db.flush()
    assert course.id is not None
    return course.id


async def _create_server(db: AsyncSession, *, server_id: int, name: str) -> None:
    db.add(
        ServerGlobalapi(
            id=server_id,
            port=27015,
            ip="203.0.113.60",
            name=name,
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
        is_valid=True,
    )
    await db.flush()


async def _rebuild_player_scope(
    db: AsyncSession,
    *,
    scope_id: int,
    steamid64: int,
) -> None:
    await crud.rebuild_leaderboard_player(
        session=db,
        scope_id=scope_id,
        steamid64=steamid64,
    )
    await db.commit()


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


async def test_rebuild_leaderboard_player_aggregates_points_ratings_and_thresholds(
    db: AsyncSession,
) -> None:
    player_id = random_steamid64()
    server_id = 2_100_000_001
    await _create_player(db, steamid64=player_id, name="Leaderboard One")
    await _create_server(db, server_id=server_id, name="Leaderboard Server")

    for index in range(10):
        map_id = 2_100_100_000 + index
        tier = 4 if index < 10 else 5
        course_id = await _create_map(
            db,
            map_id=map_id,
            name=f"kz_lb_{index}",
            difficulty=tier,
        )
        del course_id
        await _create_record_filter(
            db,
            record_filter_id=2_100_200_000 + index,
            map_id=map_id,
            mode_id=200,
            tier=tier,
        )
        await _create_record(
            db,
            record_id=2_100_300_000 + index,
            steamid64=player_id,
            server_id=server_id,
            map_id=map_id,
            mode_id=200,
            teleports=1,
            time_seconds=f"{10 + index}.000",
        )

    await _create_record(
        db,
        record_id=2_100_400_000,
        steamid64=player_id,
        server_id=server_id,
        map_id=2_100_100_000,
        mode_id=200,
        teleports=0,
        time_seconds="9.000",
    )

    await _rebuild_player_scope(
        db,
        scope_id=int(RecordScopeId.KZT),
        steamid64=player_id,
    )

    row = await db.get(LeaderboardPlayer, (int(RecordScopeId.KZT), player_id))
    assert row is not None
    assert row.points == 11_000
    assert row.wrs_nub == 10
    assert row.wrs_pro == 1
    assert row.records_900_plus == 10
    assert row.records_800_plus == 10
    assert row.unique_map_finishes == 10
    assert row.rating == crud.calculate_weighted_rating([1000] * 10)
    assert row.rating_easy == crud.calculate_weighted_rating([1000] * 10)
    assert row.rating_hard == 0


async def test_build_leaderboard_values_counts_high_point_records_once_per_map() -> None:
    values = _build_leaderboard_values(
        rows=[
            (101, 1001, False, 870),
            (101, 1001, True, 930),
            (102, 1002, False, 920),
            (102, 1002, True, 810),
            (103, 1003, False, 790),
        ],
        tiers_by_course_id={101: 4, 102: 4, 103: 5},
    )

    assert values["records_900_plus"] == 2
    assert values["records_800_plus"] == 2
    assert values["unique_map_finishes"] == 3


async def test_rebuild_leaderboard_player_deletes_row_below_threshold(
    db: AsyncSession,
) -> None:
    player_id = random_steamid64()
    server_id = 2_110_000_001
    await _create_player(db, steamid64=player_id, name="Threshold Player")
    await _create_server(db, server_id=server_id, name="Threshold Server")

    for index in range(9):
        map_id = 2_110_100_000 + index
        course_id = await _create_map(
            db,
            map_id=map_id,
            name=f"kz_threshold_{index}",
            difficulty=4,
        )
        del course_id
        await _create_record_filter(
            db,
            record_filter_id=2_110_200_000 + index,
            map_id=map_id,
            mode_id=200,
            tier=4,
        )
        await _create_record(
            db,
            record_id=2_110_300_000 + index,
            steamid64=player_id,
            server_id=server_id,
            map_id=map_id,
            mode_id=200,
            teleports=1,
            time_seconds=f"{20 + index}.000",
        )

    await _rebuild_player_scope(
        db,
        scope_id=int(RecordScopeId.KZT),
        steamid64=player_id,
    )

    row = await db.get(LeaderboardPlayer, (int(RecordScopeId.KZT), player_id))
    assert row is None


async def test_rebuild_leaderboard_player_deletes_existing_row_for_active_ban(
    db: AsyncSession,
) -> None:
    player_id = random_steamid64()
    server_id = 2_115_000_001
    await _create_player(db, steamid64=player_id, name="Banned Player")
    await _create_server(db, server_id=server_id, name="Banned Server")

    for index in range(10):
        map_id = 2_115_100_000 + index
        await _create_map(
            db,
            map_id=map_id,
            name=f"kz_banned_{index}",
            difficulty=4,
        )
        await _create_record_filter(
            db,
            record_filter_id=2_115_200_000 + index,
            map_id=map_id,
            mode_id=200,
            tier=4,
        )
        await _create_record(
            db,
            record_id=2_115_300_000 + index,
            steamid64=player_id,
            server_id=server_id,
            map_id=map_id,
            mode_id=200,
            teleports=1,
            time_seconds=f"{30 + index}.000",
        )

    await _rebuild_player_scope(
        db,
        scope_id=int(RecordScopeId.KZT),
        steamid64=player_id,
    )
    assert await db.get(LeaderboardPlayer, (int(RecordScopeId.KZT), player_id)) is not None

    await _create_ban(
        db,
        ban_id=2_115_400_000,
        steamid64=player_id,
        expires_on=None,
    )
    await _rebuild_player_scope(
        db,
        scope_id=int(RecordScopeId.KZT),
        steamid64=player_id,
    )

    assert await db.get(LeaderboardPlayer, (int(RecordScopeId.KZT), player_id)) is None


async def test_load_leaderboard_player_keys_prioritizes_existing_rating_before_new_keys(
    db: AsyncSession,
) -> None:
    first_player = random_steamid64()
    second_player = random_steamid64()
    newcomer = random_steamid64()
    server_id = 2_120_000_001
    scope_id = int(RecordScopeId.KZT)

    await _create_player(db, steamid64=first_player, name="First Existing")
    await _create_player(db, steamid64=second_player, name="Second Existing")
    await _create_player(db, steamid64=newcomer, name="Newcomer")
    await _create_server(db, server_id=server_id, name="Priority Server")

    for index in range(10):
        map_id = 2_120_100_000 + index
        await _create_map(
            db,
            map_id=map_id,
            name=f"kz_priority_{index}",
            difficulty=4,
        )
        await _create_record_filter(
            db,
            record_filter_id=2_120_200_000 + index,
            map_id=map_id,
            mode_id=200,
            tier=4,
        )
        await _create_record(
            db,
            record_id=2_120_300_000 + index,
            steamid64=newcomer,
            server_id=server_id,
            map_id=map_id,
            mode_id=200,
            teleports=1,
            time_seconds=f"{15 + index}.000",
        )

    db.add(
        LeaderboardPlayer(
            scope=scope_id,
            steamid64=first_player,
            rating=100,
        )
    )
    db.add(
        LeaderboardPlayer(
            scope=scope_id,
            steamid64=second_player,
            rating=300,
        )
    )
    await db.commit()

    keys = await crud.load_leaderboard_player_keys(
        session=db,
        scope_ids=[scope_id],
        prioritize_existing_rating=True,
    )

    assert keys == [
        (scope_id, second_player),
        (scope_id, first_player),
        (scope_id, newcomer),
    ]


async def test_load_leaderboard_player_keys_filters_source_keys_to_eligible_unbanned_players(
    db: AsyncSession,
) -> None:
    eligible_player = random_steamid64()
    ineligible_player = random_steamid64()
    banned_player = random_steamid64()
    stale_existing_player = random_steamid64()
    server_id = 2_130_000_001
    scope_id = int(RecordScopeId.KZT)

    await _create_player(db, steamid64=eligible_player, name="Eligible Player")
    await _create_player(db, steamid64=ineligible_player, name="Ineligible Player")
    await _create_player(db, steamid64=banned_player, name="Banned Player")
    await _create_player(db, steamid64=stale_existing_player, name="Stale Existing")
    await _create_server(db, server_id=server_id, name="Eligible Keys Server")

    for index in range(10):
        map_id = 2_130_100_000 + index
        await _create_map(
            db,
            map_id=map_id,
            name=f"kz_keys_{index}",
            difficulty=4,
        )
        await _create_record_filter(
            db,
            record_filter_id=2_130_200_000 + index,
            map_id=map_id,
            mode_id=200,
            tier=4,
        )
        await _create_record(
            db,
            record_id=2_130_300_000 + index,
            steamid64=eligible_player,
            server_id=server_id,
            map_id=map_id,
            mode_id=200,
            teleports=1,
            time_seconds=f"{20 + index}.000",
        )
        await _create_record(
            db,
            record_id=2_130_400_000 + index,
            steamid64=banned_player,
            server_id=server_id,
            map_id=map_id,
            mode_id=200,
            teleports=1,
            time_seconds=f"{40 + index}.000",
        )
        if index < 9:
            await _create_record(
                db,
                record_id=2_130_500_000 + index,
                steamid64=ineligible_player,
                server_id=server_id,
                map_id=map_id,
                mode_id=200,
                teleports=1,
                time_seconds=f"{60 + index}.000",
            )

    await _create_ban(
        db,
        ban_id=2_130_600_000,
        steamid64=banned_player,
        expires_on=None,
    )
    db.add(
        LeaderboardPlayer(
            scope=scope_id,
            steamid64=stale_existing_player,
            rating=123,
        )
    )
    await db.commit()

    keys = await crud.load_leaderboard_player_keys(
        session=db,
        scope_ids=[scope_id],
    )

    assert keys == [
        (scope_id, eligible_player),
        (scope_id, stale_existing_player),
    ]
