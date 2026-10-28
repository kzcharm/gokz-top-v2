from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlmodel import delete, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.models import (
    Map,
    Player,
    PlayerAction,
    PlayerActionTimestamp,
    PlayerStatCache,
    PlayerStatType,
    Record,
    RecordPb,
    ServerGlobalapi,
)
from tests.utils.server import create_server_group as create_test_server_group
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


async def _create_player(db: AsyncSession, *, steamid64: int, name: str) -> None:
    await db.exec(delete(Player).where(Player.steamid64 == steamid64))
    await db.commit()
    db.add(Player(steamid64=steamid64, name=name))
    await db.commit()


async def _create_map(
    db: AsyncSession,
    *,
    id: int,
    name: str,
    difficulty: int = 2,
) -> None:
    await db.exec(delete(Map).where(Map.id == id))
    await db.commit()
    db.add(
        Map(
            id=id,
            name=name,
            filesize=1,
            validated=True,
            difficulty=difficulty,
            approved_by_steamid64=76561198003275951,
        )
    )
    await db.commit()


async def _create_server(
    db: AsyncSession,
    *,
    id: int,
    name: str,
    group_id=None,
) -> None:
    await db.exec(delete(ServerGlobalapi).where(ServerGlobalapi.id == id))
    await db.commit()
    for steamid64 in (76561198000000010, 76561198000000020):
        if await db.get(Player, steamid64) is None:
            db.add(Player(steamid64=steamid64, name=str(steamid64)))

    db.add(
        ServerGlobalapi(
            id=id,
            port=27015,
            ip=f"203.0.113.{id % 255}",
            name=name,
            group_id=group_id,
            owner_steamid64=76561198000000010,
            approval_status=1,
            approved_by_steamid64=76561198000000020,
        )
    )
    await db.commit()


async def _create_record(
    db: AsyncSession,
    *,
    id: int,
    steamid64: int,
    map_id: int,
    server_id: int,
    created_on: datetime,
    time_seconds: str,
) -> None:
    record_uuid_subquery = select(Record.uuid).where(Record.id == id)
    await db.exec(
        delete(RecordPb).where(RecordPb.record_uuid.in_(record_uuid_subquery))
    )
    await db.exec(delete(Record).where(Record.id == id))
    await db.commit()
    await crud.upsert_record(
        session=db,
        record_id=id,
        record_uuid=None,
        steamid64=steamid64,
        server_id=server_id,
        mode_id=200,
        map_id=map_id,
        stage=0,
        time_seconds=Decimal(time_seconds),
        teleports=1,
        points=0,
        created_on=created_on,
        updated_on=created_on,
        updated_by=steamid64,
        replay_id=None,
        is_valid=True,
    )
    await db.commit()


@pytest.mark.asyncio
async def test_player_stats_cache_table_exists(db: AsyncSession) -> None:
    table_name = await db.exec(text("SELECT to_regclass('cache.player_stats')"))
    assert table_name.one()[0] == "cache.player_stats"


@pytest.mark.asyncio
async def test_rebuild_player_daily_activity_stat_upserts_existing_cache_row(
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    first_now = datetime(2026, 4, 2, 12, 0, tzinfo=UTC)
    second_now = datetime(2026, 4, 3, 12, 0, tzinfo=UTC)
    await _create_player(db, steamid64=steamid64, name="Cache Runner")
    await _create_map(db, id=981200, name="kz_cache")
    await _create_server(db, id=982200, name="Cache Server")
    await _create_record(
        db,
        id=983200,
        steamid64=steamid64,
        map_id=981200,
        server_id=982200,
        created_on=datetime(2026, 4, 2, 8, 0, tzinfo=UTC),
        time_seconds="20.000",
    )

    first_stat = await crud.rebuild_player_daily_activity_stat(
        session=db,
        steamid64=steamid64,
        now=first_now,
    )

    await _create_record(
        db,
        id=983201,
        steamid64=steamid64,
        map_id=981200,
        server_id=982200,
        created_on=datetime(2026, 4, 2, 23, 0, tzinfo=UTC),
        time_seconds="20.000",
    )

    second_stat = await crud.rebuild_player_daily_activity_stat(
        session=db,
        steamid64=steamid64,
        now=second_now,
    )

    assert first_stat.content.model_dump(mode="json") == {
        "days": [{"date": "2026-04-02", "count": 1, "total_seconds": 20.0}]
    }
    assert second_stat.content.model_dump(mode="json") == {
        "days": [{"date": "2026-04-02", "count": 2, "total_seconds": 40.0}]
    }

    cache_rows = (
        await db.exec(
            select(func.count())
            .select_from(PlayerStatCache)
            .where(
                PlayerStatCache.steamid64 == steamid64,
                PlayerStatCache.type == PlayerStatType.DAILY_ACTIVITY,
            )
        )
    ).one()
    assert cache_rows == 1

    cache_row = await db.get(
        PlayerStatCache, (steamid64, PlayerStatType.DAILY_ACTIVITY)
    )
    assert cache_row is not None
    assert cache_row.updated_at == second_now
    assert cache_row.content == {
        "version": 2,
        "days": [{"date": "2026-04-02", "count": 2, "total_seconds": 40.0}],
    }


@pytest.mark.asyncio
async def test_record_upsert_refreshes_cached_daily_activity_for_record_date(
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    await _create_player(db, steamid64=steamid64, name="Late Sync Runner")
    await _create_map(db, id=981201, name="kz_late_sync")
    await _create_server(db, id=982201, name="Late Sync Server")
    await _create_record(
        db,
        id=983202,
        steamid64=steamid64,
        map_id=981201,
        server_id=982201,
        created_on=datetime(2026, 4, 1, 8, 0, tzinfo=UTC),
        time_seconds="20.000",
    )
    await _create_record(
        db,
        id=983203,
        steamid64=steamid64,
        map_id=981201,
        server_id=982201,
        created_on=datetime(2026, 4, 3, 8, 0, tzinfo=UTC),
        time_seconds="20.000",
    )
    await crud.rebuild_player_daily_activity_stat(
        session=db,
        steamid64=steamid64,
        now=datetime(2026, 4, 4, 12, 0, tzinfo=UTC),
    )

    await _create_record(
        db,
        id=983204,
        steamid64=steamid64,
        map_id=981201,
        server_id=982201,
        created_on=datetime(2026, 4, 1, 23, 0, tzinfo=UTC),
        time_seconds="20.000",
    )

    cache_row = await db.get(
        PlayerStatCache,
        (steamid64, PlayerStatType.DAILY_ACTIVITY),
    )
    assert cache_row is not None
    assert cache_row.content == {
        "version": 2,
        "days": [
            {"date": "2026-04-01", "count": 2, "total_seconds": 40.0},
            {"date": "2026-04-03", "count": 1, "total_seconds": 20.0},
        ],
    }


@pytest.mark.asyncio
async def test_record_upsert_refreshes_old_and_new_daily_activity_dates(
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    record_id = 983205
    await _create_player(db, steamid64=steamid64, name="Moved Sync Runner")
    await _create_map(db, id=981202, name="kz_moved_sync")
    await _create_server(db, id=982202, name="Moved Sync Server")
    await _create_record(
        db,
        id=record_id,
        steamid64=steamid64,
        map_id=981202,
        server_id=982202,
        created_on=datetime(2026, 4, 1, 8, 0, tzinfo=UTC),
        time_seconds="20.000",
    )
    await crud.rebuild_player_daily_activity_stat(
        session=db,
        steamid64=steamid64,
        now=datetime(2026, 4, 4, 12, 0, tzinfo=UTC),
    )

    await crud.upsert_record(
        session=db,
        record_id=record_id,
        record_uuid=None,
        steamid64=steamid64,
        server_id=982202,
        mode_id=200,
        map_id=981202,
        stage=0,
        time_seconds=Decimal("19.000"),
        teleports=1,
        points=0,
        created_on=datetime(2026, 4, 2, 8, 0, tzinfo=UTC),
        updated_on=datetime(2026, 4, 2, 8, 0, tzinfo=UTC),
        updated_by=steamid64,
        replay_id=None,
        is_valid=True,
    )
    await db.commit()

    cache_row = await db.get(
        PlayerStatCache,
        (steamid64, PlayerStatType.DAILY_ACTIVITY),
    )
    assert cache_row is not None
    assert cache_row.content == {
        "version": 2,
        "days": [{"date": "2026-04-02", "count": 1, "total_seconds": 19.0}],
    }


@pytest.mark.asyncio
async def test_rebuild_player_playtime_stat_upserts_existing_cache_row(
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    first_now = datetime(2026, 4, 2, 12, 0, tzinfo=UTC)
    second_now = datetime(2026, 4, 3, 12, 0, tzinfo=UTC)
    await _create_player(db, steamid64=steamid64, name="Playtime Runner")
    await _create_map(db, id=981210, name="kz_playtime")
    await _create_server(db, id=982210, name="Playtime Server")
    await _create_record(
        db,
        id=983210,
        steamid64=steamid64,
        map_id=981210,
        server_id=982210,
        created_on=datetime(2026, 4, 2, 8, 0, tzinfo=UTC),
        time_seconds="12.500",
    )

    first_stat = await crud.rebuild_player_playtime_stat(
        session=db,
        steamid64=steamid64,
        now=first_now,
    )

    await _create_record(
        db,
        id=983211,
        steamid64=steamid64,
        map_id=981210,
        server_id=982210,
        created_on=datetime(2026, 4, 2, 23, 0, tzinfo=UTC),
        time_seconds="7.500",
    )
    await _create_record(
        db,
        id=983212,
        steamid64=steamid64,
        map_id=981210,
        server_id=982210,
        created_on=datetime(2026, 4, 3, 9, 0, tzinfo=UTC),
        time_seconds="5.000",
    )

    second_stat = await crud.rebuild_player_playtime_stat(
        session=db,
        steamid64=steamid64,
        now=second_now,
    )

    assert first_stat.content.total_seconds == 12.5
    assert second_stat.content.total_seconds == 25.0

    cache_rows = (
        await db.exec(
            select(func.count())
            .select_from(PlayerStatCache)
            .where(
                PlayerStatCache.steamid64 == steamid64,
                PlayerStatCache.type == PlayerStatType.DAILY_ACTIVITY,
            )
        )
    ).one()
    assert cache_rows == 1

    cache_row = await db.get(
        PlayerStatCache, (steamid64, PlayerStatType.DAILY_ACTIVITY)
    )
    assert cache_row is not None
    assert cache_row.updated_at == second_now
    assert sum(day["total_seconds"] for day in cache_row.content["days"]) == 25.0
    assert await db.get(PlayerStatCache, (steamid64, PlayerStatType.PLAYTIME)) is None


@pytest.mark.asyncio
async def test_rebuild_player_most_played_server_stat_groups_by_server_group(
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    now = datetime(2026, 4, 4, 12, 0, tzinfo=UTC)
    await _create_player(db, steamid64=steamid64, name="Grouped Runner")
    await _create_map(db, id=981230, name="kz_grouped")
    grouped_server_group, _ = await create_test_server_group(
        db,
        name=f"FemboyKZ | EU | Public | 128t VNL Global {steamid64}",
    )
    solo_server_group, _ = await create_test_server_group(
        db,
        name=f"House of Climb NA GOKZ #1 {steamid64}",
    )
    await _create_server(
        db,
        id=982230,
        name="FemboyKZ | EU | Public | 128t VNL Global #1",
        group_id=grouped_server_group.id,
    )
    await _create_server(
        db,
        id=982231,
        name="FemboyKZ | EU | Public | 128t VNL Global #2",
        group_id=grouped_server_group.id,
    )
    await _create_server(
        db,
        id=982232,
        name="House of Climb NA GOKZ #1",
        group_id=solo_server_group.id,
    )
    await _create_record(
        db,
        id=983230,
        steamid64=steamid64,
        map_id=981230,
        server_id=982230,
        created_on=datetime(2024, 1, 15, 8, 0, tzinfo=UTC),
        time_seconds="10.000",
    )
    await _create_record(
        db,
        id=983231,
        steamid64=steamid64,
        map_id=981230,
        server_id=982231,
        created_on=datetime(2025, 2, 15, 8, 0, tzinfo=UTC),
        time_seconds="15.000",
    )
    await _create_record(
        db,
        id=983232,
        steamid64=steamid64,
        map_id=981230,
        server_id=982232,
        created_on=datetime(2025, 11, 15, 8, 0, tzinfo=UTC),
        time_seconds="20.000",
    )
    await _create_record(
        db,
        id=983233,
        steamid64=steamid64,
        map_id=981230,
        server_id=982230,
        created_on=datetime(2026, 3, 15, 8, 0, tzinfo=UTC),
        time_seconds="5.000",
    )

    stat = await crud.rebuild_player_most_played_server_stat(
        session=db,
        steamid64=steamid64,
        now=now,
    )

    assert stat.content.first_year == 2024
    assert stat.content.current_year == 2026
    assert stat.content.years == [2024, 2025, 2026]
    assert stat.content.all_time.total_seconds == 50.0
    assert stat.content.last_365_days.total_seconds == 25.0
    assert stat.content.yearly["2024"].total_seconds == 10.0
    assert stat.content.yearly["2025"].total_seconds == 35.0
    assert stat.content.yearly["2026"].total_seconds == 5.0
    assert stat.content.all_time.entries[0].label == grouped_server_group.name
    assert stat.content.all_time.entries[0].server_count == 2
    assert stat.content.all_time.entries[0].server_ids == [982230, 982231]
    assert stat.content.all_time.entries[1].label == solo_server_group.name

    grouped_server_group_id = grouped_server_group.id
    db.expire_all()
    player = await db.get(Player, steamid64)
    assert player is not None
    assert player.favorite_server_id is None
    assert player.favorite_server_group_id == grouped_server_group_id


@pytest.mark.asyncio
async def test_rebuild_player_most_played_maps_stat_aggregates_periods_and_rankings(
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    now = datetime(2026, 4, 4, 12, 0, tzinfo=UTC)
    await _create_player(db, steamid64=steamid64, name="Map Stats Runner")
    await _create_map(db, id=981260, name="kz_records", difficulty=3)
    await _create_map(db, id=981261, name="kz_hours", difficulty=5)
    await _create_map(db, id=981262, name="kz_old", difficulty=1)
    await _create_server(db, id=982260, name="Map Stats Server")
    await _create_record(
        db,
        id=983260,
        steamid64=steamid64,
        map_id=981260,
        server_id=982260,
        created_on=datetime(2026, 4, 2, 8, 0, tzinfo=UTC),
        time_seconds="10.000",
    )
    await _create_record(
        db,
        id=983261,
        steamid64=steamid64,
        map_id=981260,
        server_id=982260,
        created_on=datetime(2026, 4, 2, 9, 0, tzinfo=UTC),
        time_seconds="10.000",
    )
    await _create_record(
        db,
        id=983262,
        steamid64=steamid64,
        map_id=981261,
        server_id=982260,
        created_on=datetime(2025, 5, 1, 8, 0, tzinfo=UTC),
        time_seconds="45.000",
    )
    await _create_record(
        db,
        id=983263,
        steamid64=steamid64,
        map_id=981262,
        server_id=982260,
        created_on=datetime(2024, 1, 1, 8, 0, tzinfo=UTC),
        time_seconds="30.000",
    )

    stat = await crud.rebuild_player_most_played_maps_stat(
        session=db,
        steamid64=steamid64,
        now=now,
    )

    assert stat.content.first_year == 2024
    assert stat.content.current_year == 2026
    assert stat.content.years == [2024, 2025, 2026]
    assert stat.content.all_time.total_records == 4
    assert stat.content.all_time.total_seconds == 95.0
    assert [entry.map_name for entry in stat.content.all_time.entries_by_records] == [
        "kz_records",
        "kz_hours",
        "kz_old",
    ]
    assert [entry.map_name for entry in stat.content.all_time.entries_by_time] == [
        "kz_hours",
        "kz_old",
        "kz_records",
    ]
    assert stat.content.all_time.entries_by_records[0].map_tier == 3
    assert stat.content.all_time.entries_by_records[0].record_count == 2
    assert stat.content.all_time.entries_by_records[0].total_seconds == 20.0
    assert stat.content.last_365_days.total_records == 3
    assert stat.content.last_365_days.total_seconds == 65.0
    assert stat.content.yearly["2024"].entries_by_records[0].map_name == "kz_old"
    assert stat.content.yearly["2025"].entries_by_records[0].map_name == "kz_hours"
    assert stat.content.yearly["2026"].entries_by_records[0].map_name == "kz_records"

    cache_row = await db.get(
        PlayerStatCache, (steamid64, PlayerStatType.MOST_PLAYED_MAPS)
    )
    assert cache_row is not None
    assert cache_row.updated_at == now


@pytest.mark.asyncio
async def test_rebuild_player_most_played_maps_stat_handles_empty_player(
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    now = datetime(2026, 4, 4, 12, 0, tzinfo=UTC)
    await _create_player(db, steamid64=steamid64, name="Empty Map Stats Runner")

    stat = await crud.rebuild_player_most_played_maps_stat(
        session=db,
        steamid64=steamid64,
        now=now,
    )

    assert stat.content.model_dump() == {
        "first_year": None,
        "current_year": None,
        "years": [],
        "all_time": {
            "total_records": 0,
            "total_seconds": 0.0,
            "entries_by_records": [],
            "entries_by_time": [],
        },
        "last_365_days": {
            "total_records": 0,
            "total_seconds": 0.0,
            "entries_by_records": [],
            "entries_by_time": [],
        },
        "yearly": {},
    }


@pytest.mark.asyncio
async def test_rebuild_player_most_played_maps_stat_limits_rankings_to_top_10(
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    now = datetime(2026, 4, 4, 12, 0, tzinfo=UTC)
    await _create_player(db, steamid64=steamid64, name="Top Ten Map Runner")
    await _create_server(db, id=982270, name="Top Ten Map Server")
    for index in range(12):
        map_id = 981270 + index
        await _create_map(db, id=map_id, name=f"kz_top_{index:02d}")
        await _create_record(
            db,
            id=983270 + index,
            steamid64=steamid64,
            map_id=map_id,
            server_id=982270,
            created_on=datetime(2026, 4, 2, 8, index, tzinfo=UTC),
            time_seconds=f"{100 - index}.000",
        )

    stat = await crud.rebuild_player_most_played_maps_stat(
        session=db,
        steamid64=steamid64,
        now=now,
    )

    assert stat.content.all_time.total_records == 12
    assert len(stat.content.all_time.entries_by_records) == 10
    assert len(stat.content.all_time.entries_by_time) == 10
    assert stat.content.all_time.entries_by_time[-1].map_name == "kz_top_09"
    assert all(
        entry.map_name != "kz_top_10" for entry in stat.content.all_time.entries_by_time
    )


@pytest.mark.asyncio
async def test_rebuild_player_most_played_server_stat_auto_updates_ungrouped_favorite(
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    now = datetime(2026, 4, 3, 12, 0, tzinfo=UTC)
    await _create_player(db, steamid64=steamid64, name="Favorite Runner")
    await _create_map(db, id=981240, name="kz_favorite")
    await _create_server(db, id=982240, name="Favorite One")
    await _create_server(db, id=982241, name="Favorite Two")
    await _create_record(
        db,
        id=983240,
        steamid64=steamid64,
        map_id=981240,
        server_id=982240,
        created_on=datetime(2026, 4, 2, 8, 0, tzinfo=UTC),
        time_seconds="10.000",
    )
    await _create_record(
        db,
        id=983241,
        steamid64=steamid64,
        map_id=981240,
        server_id=982241,
        created_on=datetime(2026, 4, 2, 9, 0, tzinfo=UTC),
        time_seconds="20.000",
    )

    await crud.rebuild_player_most_played_server_stat(
        session=db,
        steamid64=steamid64,
        now=now,
    )

    db.expire_all()
    player = await db.get(Player, steamid64)
    assert player is not None
    assert player.favorite_server_id == 982241
    assert player.favorite_server_group_id is None


@pytest.mark.asyncio
async def test_rebuild_player_most_played_server_stat_skips_manual_none_override(
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    now = datetime(2026, 4, 3, 12, 0, tzinfo=UTC)
    await _create_player(db, steamid64=steamid64, name="Favorite None Runner")
    await _create_map(db, id=981250, name="kz_favorite_none")
    await _create_server(db, id=982250, name="Favorite None")
    await _create_record(
        db,
        id=983250,
        steamid64=steamid64,
        map_id=981250,
        server_id=982250,
        created_on=datetime(2026, 4, 2, 8, 0, tzinfo=UTC),
        time_seconds="10.000",
    )
    db.add(
        PlayerActionTimestamp(
            player_steamid64=steamid64,
            action=PlayerAction.FAVORITE_SERVER_MANUAL_OVERRIDE,
            recorded_at=now,
        )
    )
    await db.commit()

    await crud.rebuild_player_most_played_server_stat(
        session=db,
        steamid64=steamid64,
        now=now,
    )

    db.expire_all()
    player = await db.get(Player, steamid64)
    assert player is not None
    assert player.favorite_server_id is None
    assert player.favorite_server_group_id is None


@pytest.mark.asyncio
async def test_get_or_rebuild_player_stats_returns_requested_fields(
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    now = datetime(2026, 4, 2, 12, 0, tzinfo=UTC)
    await _create_player(db, steamid64=steamid64, name="Combined Runner")
    await _create_map(db, id=981220, name="kz_combined")
    await _create_server(db, id=982220, name="Combined Server")
    await _create_record(
        db,
        id=983220,
        steamid64=steamid64,
        map_id=981220,
        server_id=982220,
        created_on=datetime(2026, 4, 2, 8, 0, tzinfo=UTC),
        time_seconds="9.500",
    )

    stats = await crud.get_or_rebuild_player_stats(
        session=db,
        steamid64=steamid64,
        now=now,
    )
    filtered_stats = await crud.get_or_rebuild_player_stats(
        session=db,
        steamid64=steamid64,
        stat_type=PlayerStatType.PLAYTIME,
        now=now,
    )

    assert stats.daily_activity is not None
    assert stats.daily_activity.days[0].count == 1
    assert stats.playtime is not None
    assert stats.playtime.total_seconds == 9.5
    assert stats.most_played_maps is not None
    assert stats.most_played_maps.all_time.total_records == 1
    assert (
        stats.most_played_maps.all_time.entries_by_records[0].map_name == "kz_combined"
    )
    assert filtered_stats.daily_activity is None
    assert filtered_stats.playtime is not None
    assert filtered_stats.playtime.total_seconds == 9.5
    assert filtered_stats.most_played_maps is None


async def test_combined_activity_merges_sessions_and_excludes_covered_finishes(
    db: AsyncSession,
) -> None:
    from datetime import timedelta

    from app.models import PlayerSession, PlayerSessionDisconnect, generate_uuid7

    steamid64 = random_steamid64()
    await _create_player(db, steamid64=steamid64, name="Session runner")
    group, _ = await create_test_server_group(db)
    other_group, _ = await create_test_server_group(db)
    await _create_map(db, id=981299, name="kz_sessions")
    await _create_server(db, id=982299, name="Sessions")
    start = datetime(2025, 12, 31, 23, tzinfo=UTC)
    sessions = []
    for offset, end, target_group in [
        (0, 2, group),
        (1, 3, other_group),
        (48, None, group),
    ]:
        row = PlayerSession(
            id=generate_uuid7(),
            player_steamid64=steamid64,
            server_group_id=target_group.id,
            connected_at=start + timedelta(hours=offset),
            disconnect_at=start + timedelta(hours=end) if end is not None else None,
            last_heartbeat_at=start + timedelta(hours=end if end is not None else 49),
            ip_address="127.0.0.1",
            map_name="kz_sessions",
        )
        db.add(row)
        sessions.append(row)
    await db.commit()
    # Start, interior and end are covered. Outside and open-session finishes remain fallback time.
    for index, hours in enumerate([-1, 0, 1, 3, 49]):
        await _create_record(
            db,
            id=983290 + index,
            steamid64=steamid64,
            map_id=981299,
            server_id=982299,
            created_on=start + timedelta(hours=hours),
            time_seconds="60.000",
        )
    now = start + timedelta(days=4)
    activity = await crud.get_or_rebuild_player_daily_activity_stat(
        session=db, steamid64=steamid64, now=now
    )
    assert activity.content.model_dump(mode="json")["days"] == [
        {"date": "2025-12-31", "count": 2, "total_seconds": 3660.0},
        {"date": "2026-01-01", "count": 2, "total_seconds": 7200.0},
        {"date": "2026-01-03", "count": 1, "total_seconds": 60.0},
    ]
    total = await crud.get_or_rebuild_player_playtime_stat(
        session=db, steamid64=steamid64, now=now
    )
    assert total.content.total_seconds == 10920
    # Closing a session replaces fallback runtime and adds the previously session-only day.
    await crud.disconnect_player_session(
        session=db,
        group=group,
        payload=PlayerSessionDisconnect(
            session_id=sessions[-1].id, disconnect_at=start + timedelta(hours=50)
        ),
    )
    assert (
        await db.get(PlayerStatCache, (steamid64, PlayerStatType.DAILY_ACTIVITY))
        is None
    )
    total = await crud.get_or_rebuild_player_playtime_stat(
        session=db, steamid64=steamid64, now=now
    )
    assert total.content.total_seconds == 18060
    activity = await crud.get_or_rebuild_player_daily_activity_stat(
        session=db, steamid64=steamid64, now=now
    )
    assert any(
        day.count == 0 and day.total_seconds == 3600 for day in activity.content.days
    )
    # A delayed finish in a covered session must refresh counts without adding runtime.
    await _create_record(
        db,
        id=983299,
        steamid64=steamid64,
        map_id=981299,
        server_id=982299,
        created_on=start + timedelta(minutes=30),
        time_seconds="120.000",
    )
    total = await crud.get_or_rebuild_player_playtime_stat(
        session=db, steamid64=steamid64, now=now
    )
    assert total.content.total_seconds == 18060


async def test_activity_upgrades_legacy_cache_and_timeout_invalidates(
    db: AsyncSession,
) -> None:
    from datetime import timedelta

    from app.models import PlayerSession, generate_uuid7

    steamid64 = random_steamid64()
    await _create_player(db, steamid64=steamid64, name="Legacy session")
    group, _ = await create_test_server_group(db)
    now = datetime(2026, 4, 4, 12, tzinfo=UTC)
    db.add(
        PlayerStatCache(
            steamid64=steamid64,
            type=PlayerStatType.DAILY_ACTIVITY,
            content={"days": [{"date": "2020-01-01", "count": 999}]},
            updated_at=now,
        )
    )
    db.add(
        PlayerStatCache(
            steamid64=steamid64,
            type=PlayerStatType.PLAYTIME,
            content={"total_seconds": 999999},
            updated_at=now,
        )
    )
    db.add(
        PlayerSession(
            id=generate_uuid7(),
            player_steamid64=steamid64,
            server_group_id=group.id,
            connected_at=now - timedelta(hours=2),
            last_heartbeat_at=now - timedelta(hours=1),
            ip_address="127.0.0.1",
            map_name="kz_session",
        )
    )
    await db.commit()
    total = await crud.get_or_rebuild_player_playtime_stat(
        session=db, steamid64=steamid64, now=now
    )
    assert total.content.total_seconds == 0
    await crud.close_timed_out_player_sessions(
        session=db, now=now, timeout=timedelta(minutes=5)
    )
    total = await crud.get_or_rebuild_player_playtime_stat(
        session=db, steamid64=steamid64, now=now
    )
    assert total.content.total_seconds == 3600
