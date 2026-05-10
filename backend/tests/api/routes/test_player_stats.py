from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.models import (
    Map,
    Player,
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


async def _create_map(db: AsyncSession, *, id: int, name: str) -> None:
    await db.exec(delete(Map).where(Map.id == id))
    await db.commit()
    db.add(
        Map(
            id=id,
            name=name,
            filesize=1,
            validated=True,
            difficulty=4,
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
    time_seconds: str = "20.000",
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


async def _seed_player_history(db: AsyncSession, *, steamid64: int) -> None:
    await _create_player(db, steamid64=steamid64, name="Activity Runner")
    await _create_map(db, id=981100, name="kz_activity")
    await _create_server(db, id=982100, name="Activity Server")


def _stats_url(steamid64: int, stat_type: str | None = None) -> str:
    base_url = f"{settings.API_V1_STR}/players/{steamid64}/stats"
    if stat_type is None:
        return base_url
    return f"{base_url}?type={stat_type}"


def _json_datetime(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


@pytest.mark.asyncio
async def test_read_player_stats_returns_not_found_for_missing_player(
    client: AsyncClient,
) -> None:
    response = await client.get(_stats_url(random_steamid64()))

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_read_player_stats_builds_cache_on_first_read(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steamid64 = random_steamid64()
    now = datetime(2026, 4, 2, 12, 0, tzinfo=UTC)
    await _seed_player_history(db, steamid64=steamid64)
    await _create_record(
        db,
        id=983100,
        steamid64=steamid64,
        map_id=981100,
        server_id=982100,
        created_on=datetime(2026, 4, 1, 1, 0, tzinfo=UTC),
        time_seconds="12.500",
    )
    await _create_record(
        db,
        id=983101,
        steamid64=steamid64,
        map_id=981100,
        server_id=982100,
        created_on=datetime(2026, 4, 1, 18, 0, tzinfo=UTC),
        time_seconds="7.500",
    )
    await _create_record(
        db,
        id=983102,
        steamid64=steamid64,
        map_id=981100,
        server_id=982100,
        created_on=datetime(2026, 4, 2, 0, 30, tzinfo=UTC),
        time_seconds="10.000",
    )

    monkeypatch.setattr("app.crud.player_stats.get_datetime_utc", lambda: now)

    response = await client.get(_stats_url(steamid64))

    assert response.status_code == 200
    assert response.json() == {
        "steamid64": str(steamid64),
        "daily_activity": {
            "updated_at": _json_datetime(now),
            "days": [
                {"date": "2026-04-01", "count": 2},
                {"date": "2026-04-02", "count": 1},
            ],
        },
        "playtime": {
            "updated_at": _json_datetime(now),
            "total_seconds": 30.0,
        },
        "most_played_server": {
            "updated_at": _json_datetime(now),
            "first_year": 2026,
            "current_year": 2026,
            "years": [2026],
            "all_time": {
                "total_seconds": 30.0,
                "entries": [
                    {
                        "key": "server:982100",
                        "label": "Activity Server",
                        "total_seconds": 30.0,
                        "server_count": 1,
                        "server_ids": [982100],
                    }
                ],
            },
            "last_365_days": {
                "total_seconds": 30.0,
                "entries": [
                    {
                        "key": "server:982100",
                        "label": "Activity Server",
                        "total_seconds": 30.0,
                        "server_count": 1,
                        "server_ids": [982100],
                    }
                ],
            },
            "yearly": {
                "2026": {
                    "total_seconds": 30.0,
                    "entries": [
                        {
                            "key": "server:982100",
                            "label": "Activity Server",
                            "total_seconds": 30.0,
                            "server_count": 1,
                            "server_ids": [982100],
                        }
                    ],
                }
            },
        },
    }

    daily_activity_cache = await db.get(
        PlayerStatCache, (steamid64, PlayerStatType.DAILY_ACTIVITY)
    )
    playtime_cache = await db.get(PlayerStatCache, (steamid64, PlayerStatType.PLAYTIME))
    assert daily_activity_cache is not None
    assert playtime_cache is not None


@pytest.mark.asyncio
async def test_read_player_stats_supports_type_filter(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steamid64 = random_steamid64()
    now = datetime(2026, 4, 2, 12, 0, tzinfo=UTC)
    await _seed_player_history(db, steamid64=steamid64)
    await _create_record(
        db,
        id=983105,
        steamid64=steamid64,
        map_id=981100,
        server_id=982100,
        created_on=datetime(2026, 4, 2, 8, 0, tzinfo=UTC),
        time_seconds="15.250",
    )

    monkeypatch.setattr("app.crud.player_stats.get_datetime_utc", lambda: now)

    response = await client.get(_stats_url(steamid64, "playtime"))

    assert response.status_code == 200
    assert response.json() == {
        "steamid64": str(steamid64),
        "playtime": {
            "updated_at": _json_datetime(now),
            "total_seconds": 15.25,
        },
    }


@pytest.mark.asyncio
async def test_read_player_stats_supports_most_played_server_type_filter(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steamid64 = random_steamid64()
    now = datetime(2026, 4, 2, 12, 0, tzinfo=UTC)
    await _create_player(db, steamid64=steamid64, name="Grouped Filter Runner")
    await _create_map(db, id=981130, name="kz_group_filter")
    server_group, _ = await create_test_server_group(
        db,
        name=f"House of Climb EU GOKZ VIP {steamid64}",
    )
    await _create_server(
        db,
        id=982130,
        name="House of Climb EU GOKZ VIP #1",
        group_id=server_group.id,
    )
    await _create_server(
        db,
        id=982131,
        name="House of Climb EU GOKZ VIP #2",
        group_id=server_group.id,
    )
    await _create_record(
        db,
        id=983130,
        steamid64=steamid64,
        map_id=981130,
        server_id=982130,
        created_on=datetime(2025, 8, 1, 8, 0, tzinfo=UTC),
        time_seconds="10.000",
    )
    await _create_record(
        db,
        id=983131,
        steamid64=steamid64,
        map_id=981130,
        server_id=982131,
        created_on=datetime(2026, 2, 1, 8, 0, tzinfo=UTC),
        time_seconds="15.000",
    )

    monkeypatch.setattr("app.crud.player_stats.get_datetime_utc", lambda: now)

    response = await client.get(_stats_url(steamid64, "most_played_server"))

    assert response.status_code == 200
    assert response.json() == {
        "steamid64": str(steamid64),
        "most_played_server": {
            "updated_at": _json_datetime(now),
            "first_year": 2025,
            "current_year": 2026,
            "years": [2025, 2026],
            "all_time": {
                "total_seconds": 25.0,
                "entries": [
                    {
                        "key": f"group:{server_group.id}",
                        "label": server_group.name,
                        "total_seconds": 25.0,
                        "server_count": 2,
                        "server_ids": [982130, 982131],
                        "group_id": str(server_group.id),
                    }
                ],
            },
            "last_365_days": {
                "total_seconds": 25.0,
                "entries": [
                    {
                        "key": f"group:{server_group.id}",
                        "label": server_group.name,
                        "total_seconds": 25.0,
                        "server_count": 2,
                        "server_ids": [982130, 982131],
                        "group_id": str(server_group.id),
                    }
                ],
            },
            "yearly": {
                "2025": {
                    "total_seconds": 10.0,
                    "entries": [
                        {
                            "key": f"group:{server_group.id}",
                            "label": server_group.name,
                            "total_seconds": 10.0,
                            "server_count": 1,
                            "server_ids": [982130],
                            "group_id": str(server_group.id),
                        }
                    ],
                },
                "2026": {
                    "total_seconds": 15.0,
                    "entries": [
                        {
                            "key": f"group:{server_group.id}",
                            "label": server_group.name,
                            "total_seconds": 15.0,
                            "server_count": 1,
                            "server_ids": [982131],
                            "group_id": str(server_group.id),
                        }
                    ],
                },
            },
        },
    }


@pytest.mark.asyncio
async def test_read_player_stats_uses_same_day_cache_without_refresh(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steamid64 = random_steamid64()
    first_now = datetime(2026, 4, 2, 12, 0, tzinfo=UTC)
    second_now = datetime(2026, 4, 2, 18, 0, tzinfo=UTC)
    await _seed_player_history(db, steamid64=steamid64)
    await _create_record(
        db,
        id=983110,
        steamid64=steamid64,
        map_id=981100,
        server_id=982100,
        created_on=datetime(2026, 4, 2, 8, 0, tzinfo=UTC),
        time_seconds="4.000",
    )

    monkeypatch.setattr("app.crud.player_stats.get_datetime_utc", lambda: first_now)
    first_response = await client.get(_stats_url(steamid64))

    await _create_record(
        db,
        id=983111,
        steamid64=steamid64,
        map_id=981100,
        server_id=982100,
        created_on=datetime(2026, 4, 2, 17, 0, tzinfo=UTC),
        time_seconds="6.000",
    )

    monkeypatch.setattr("app.crud.player_stats.get_datetime_utc", lambda: second_now)
    second_response = await client.get(_stats_url(steamid64))

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert second_response.json() == first_response.json()

    daily_activity_cache = await db.get(
        PlayerStatCache, (steamid64, PlayerStatType.DAILY_ACTIVITY)
    )
    playtime_cache = await db.get(PlayerStatCache, (steamid64, PlayerStatType.PLAYTIME))
    assert daily_activity_cache is not None
    assert playtime_cache is not None
    assert daily_activity_cache.updated_at == first_now
    assert playtime_cache.updated_at == first_now


@pytest.mark.asyncio
async def test_read_player_stats_refreshes_stale_cache_from_latest_cached_day(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steamid64 = random_steamid64()
    first_now = datetime(2026, 4, 2, 12, 0, tzinfo=UTC)
    refresh_now = datetime(2026, 4, 3, 12, 0, tzinfo=UTC)
    await _seed_player_history(db, steamid64=steamid64)
    await _create_record(
        db,
        id=983120,
        steamid64=steamid64,
        map_id=981100,
        server_id=982100,
        created_on=datetime(2026, 4, 1, 9, 0, tzinfo=UTC),
        time_seconds="5.000",
    )
    await _create_record(
        db,
        id=983121,
        steamid64=steamid64,
        map_id=981100,
        server_id=982100,
        created_on=datetime(2026, 4, 2, 8, 0, tzinfo=UTC),
        time_seconds="7.000",
    )

    monkeypatch.setattr("app.crud.player_stats.get_datetime_utc", lambda: first_now)
    first_response = await client.get(_stats_url(steamid64))
    assert first_response.status_code == 200

    await _create_record(
        db,
        id=983122,
        steamid64=steamid64,
        map_id=981100,
        server_id=982100,
        created_on=datetime(2026, 4, 2, 23, 30, tzinfo=UTC),
        time_seconds="11.000",
    )
    await _create_record(
        db,
        id=983123,
        steamid64=steamid64,
        map_id=981100,
        server_id=982100,
        created_on=datetime(2026, 4, 3, 4, 0, tzinfo=UTC),
        time_seconds="13.000",
    )

    monkeypatch.setattr("app.crud.player_stats.get_datetime_utc", lambda: refresh_now)
    response = await client.get(_stats_url(steamid64))

    assert response.status_code == 200
    assert response.json() == {
        "steamid64": str(steamid64),
        "daily_activity": {
            "updated_at": _json_datetime(refresh_now),
            "days": [
                {"date": "2026-04-01", "count": 1},
                {"date": "2026-04-02", "count": 2},
                {"date": "2026-04-03", "count": 1},
            ],
        },
        "playtime": {
            "updated_at": _json_datetime(refresh_now),
            "total_seconds": 36.0,
        },
        "most_played_server": {
            "updated_at": _json_datetime(refresh_now),
            "first_year": 2026,
            "current_year": 2026,
            "years": [2026],
            "all_time": {
                "total_seconds": 36.0,
                "entries": [
                    {
                        "key": "server:982100",
                        "label": "Activity Server",
                        "total_seconds": 36.0,
                        "server_count": 1,
                        "server_ids": [982100],
                    }
                ],
            },
            "last_365_days": {
                "total_seconds": 36.0,
                "entries": [
                    {
                        "key": "server:982100",
                        "label": "Activity Server",
                        "total_seconds": 36.0,
                        "server_count": 1,
                        "server_ids": [982100],
                    }
                ],
            },
            "yearly": {
                "2026": {
                    "total_seconds": 36.0,
                    "entries": [
                        {
                            "key": "server:982100",
                            "label": "Activity Server",
                            "total_seconds": 36.0,
                            "server_count": 1,
                            "server_ids": [982100],
                        }
                    ],
                }
            },
        },
    }

    daily_activity_cache = await db.get(
        PlayerStatCache, (steamid64, PlayerStatType.DAILY_ACTIVITY)
    )
    playtime_cache = await db.get(PlayerStatCache, (steamid64, PlayerStatType.PLAYTIME))
    assert daily_activity_cache is not None
    assert playtime_cache is not None
    assert daily_activity_cache.updated_at == refresh_now
    assert playtime_cache.updated_at == refresh_now


@pytest.mark.asyncio
async def test_read_player_stats_returns_empty_payload_and_writes_cache(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steamid64 = random_steamid64()
    now = datetime(2026, 4, 2, 12, 0, tzinfo=UTC)
    await _seed_player_history(db, steamid64=steamid64)

    monkeypatch.setattr("app.crud.player_stats.get_datetime_utc", lambda: now)
    response = await client.get(_stats_url(steamid64))

    assert response.status_code == 200
    assert response.json() == {
        "steamid64": str(steamid64),
        "daily_activity": {
            "updated_at": _json_datetime(now),
            "days": [],
        },
        "playtime": {
            "updated_at": _json_datetime(now),
            "total_seconds": 0.0,
        },
        "most_played_server": {
            "updated_at": _json_datetime(now),
            "first_year": None,
            "current_year": None,
            "years": [],
            "all_time": {
                "total_seconds": 0.0,
                "entries": [],
            },
            "last_365_days": {
                "total_seconds": 0.0,
                "entries": [],
            },
            "yearly": {},
        },
    }

    daily_activity_cache = await db.get(
        PlayerStatCache, (steamid64, PlayerStatType.DAILY_ACTIVITY)
    )
    playtime_cache = await db.get(PlayerStatCache, (steamid64, PlayerStatType.PLAYTIME))
    assert daily_activity_cache is not None
    assert playtime_cache is not None
