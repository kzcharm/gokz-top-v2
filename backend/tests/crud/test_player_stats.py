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
            difficulty=2,
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
        time_seconds=Decimal("20.000"),
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
    assert table_name.one() == "cache.player_stats"


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
    )

    second_stat = await crud.rebuild_player_daily_activity_stat(
        session=db,
        steamid64=steamid64,
        now=second_now,
    )

    assert first_stat.content.model_dump(mode="json") == {
        "days": [{"date": "2026-04-02", "count": 1}]
    }
    assert second_stat.content.model_dump(mode="json") == {
        "days": [{"date": "2026-04-02", "count": 2}]
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

    cache_row = await db.get(PlayerStatCache, (steamid64, PlayerStatType.DAILY_ACTIVITY))
    assert cache_row is not None
    assert cache_row.updated_at == second_now
    assert cache_row.content == {"days": [{"date": "2026-04-02", "count": 2}]}
