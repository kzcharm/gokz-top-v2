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


async def _create_server(db: AsyncSession, *, id: int, name: str) -> None:
    await db.exec(delete(ServerGlobalapi).where(ServerGlobalapi.id == id))
    await db.commit()
    db.add(
        ServerGlobalapi(
            id=id,
            port=27015,
            ip=f"203.0.113.{id % 255}",
            name=name,
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
    await db.exec(delete(RecordPb).where(RecordPb.record_uuid.in_(record_uuid_subquery)))
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


def _stat_url(steamid64: int) -> str:
    return f"{settings.API_V1_STR}/players/{steamid64}/stats/daily_activity"


@pytest.mark.asyncio
async def test_read_player_daily_activity_stat_returns_not_found_for_missing_player(
    client: AsyncClient,
) -> None:
    response = await client.get(_stat_url(random_steamid64()))

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_read_player_daily_activity_stat_builds_cache_on_first_read(
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
    )
    await _create_record(
        db,
        id=983101,
        steamid64=steamid64,
        map_id=981100,
        server_id=982100,
        created_on=datetime(2026, 4, 1, 18, 0, tzinfo=UTC),
    )
    await _create_record(
        db,
        id=983102,
        steamid64=steamid64,
        map_id=981100,
        server_id=982100,
        created_on=datetime(2026, 4, 2, 0, 30, tzinfo=UTC),
    )

    monkeypatch.setattr("app.crud.player_stats.get_datetime_utc", lambda: now)

    response = await client.get(_stat_url(steamid64))

    assert response.status_code == 200
    assert response.json() == {
        "steamid64": str(steamid64),
        "type": "daily_activity",
        "updated_at": now.isoformat(),
        "content": {
            "days": [
                {"date": "2026-04-01", "count": 2},
                {"date": "2026-04-02", "count": 1},
            ]
        },
    }

    cache_row = await db.get(PlayerStatCache, (steamid64, PlayerStatType.DAILY_ACTIVITY))
    assert cache_row is not None
    assert cache_row.content == {
        "days": [
            {"date": "2026-04-01", "count": 2},
            {"date": "2026-04-02", "count": 1},
        ]
    }
    assert cache_row.updated_at == now


@pytest.mark.asyncio
async def test_read_player_daily_activity_stat_uses_same_day_cache_without_refresh(
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
    )

    monkeypatch.setattr("app.crud.player_stats.get_datetime_utc", lambda: first_now)
    first_response = await client.get(_stat_url(steamid64))

    await _create_record(
        db,
        id=983111,
        steamid64=steamid64,
        map_id=981100,
        server_id=982100,
        created_on=datetime(2026, 4, 2, 17, 0, tzinfo=UTC),
    )

    monkeypatch.setattr("app.crud.player_stats.get_datetime_utc", lambda: second_now)
    second_response = await client.get(_stat_url(steamid64))

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert second_response.json() == first_response.json()
    assert second_response.json()["content"]["days"] == [{"date": "2026-04-02", "count": 1}]

    cache_row = await db.get(PlayerStatCache, (steamid64, PlayerStatType.DAILY_ACTIVITY))
    assert cache_row is not None
    assert cache_row.updated_at == first_now


@pytest.mark.asyncio
async def test_read_player_daily_activity_stat_refreshes_stale_cache_from_latest_cached_day(
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
    )
    await _create_record(
        db,
        id=983121,
        steamid64=steamid64,
        map_id=981100,
        server_id=982100,
        created_on=datetime(2026, 4, 2, 8, 0, tzinfo=UTC),
    )

    monkeypatch.setattr("app.crud.player_stats.get_datetime_utc", lambda: first_now)
    first_response = await client.get(_stat_url(steamid64))
    assert first_response.status_code == 200

    await _create_record(
        db,
        id=983122,
        steamid64=steamid64,
        map_id=981100,
        server_id=982100,
        created_on=datetime(2026, 4, 2, 23, 0, tzinfo=UTC),
    )
    await _create_record(
        db,
        id=983123,
        steamid64=steamid64,
        map_id=981100,
        server_id=982100,
        created_on=datetime(2026, 4, 3, 0, 1, tzinfo=UTC),
    )

    monkeypatch.setattr("app.crud.player_stats.get_datetime_utc", lambda: refresh_now)
    response = await client.get(_stat_url(steamid64))

    assert response.status_code == 200
    assert response.json() == {
        "steamid64": str(steamid64),
        "type": "daily_activity",
        "updated_at": refresh_now.isoformat(),
        "content": {
            "days": [
                {"date": "2026-04-01", "count": 1},
                {"date": "2026-04-02", "count": 2},
                {"date": "2026-04-03", "count": 1},
            ]
        },
    }

    cache_row = await db.get(PlayerStatCache, (steamid64, PlayerStatType.DAILY_ACTIVITY))
    assert cache_row is not None
    assert cache_row.updated_at == refresh_now


@pytest.mark.asyncio
async def test_read_player_daily_activity_stat_returns_empty_days_and_writes_cache(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steamid64 = random_steamid64()
    now = datetime(2026, 4, 4, 12, 0, tzinfo=UTC)
    await _seed_player_history(db, steamid64=steamid64)

    monkeypatch.setattr("app.crud.player_stats.get_datetime_utc", lambda: now)
    response = await client.get(_stat_url(steamid64))

    assert response.status_code == 200
    assert response.json() == {
        "steamid64": str(steamid64),
        "type": "daily_activity",
        "updated_at": now.isoformat(),
        "content": {"days": []},
    }

    cache_row = await db.get(PlayerStatCache, (steamid64, PlayerStatType.DAILY_ACTIVITY))
    assert cache_row is not None
    assert cache_row.content == {"days": []}
    assert cache_row.updated_at == now
