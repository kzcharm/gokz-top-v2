from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.models import Map, Player, Record, RecordPb, RecordScope, ServerGlobalapi
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
            difficulty=1,
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
    id: int | None,
    steamid64: int,
    map_id: int,
    server_id: int,
    mode_id: int,
    stage: int,
    time: str,
    teleports: int,
) -> Record:
    if id is not None:
        record_uuid_subquery = select(Record.uuid).where(Record.id == id)
        await db.exec(
            delete(RecordPb).where(RecordPb.record_uuid.in_(record_uuid_subquery))
        )
        await db.exec(delete(Record).where(Record.id == id))
        await db.commit()
    record = Record(
        id=id,
        steamid64=steamid64,
        server_id=server_id,
        mode_id=mode_id,
        map_id=map_id,
        stage=stage,
        time=Decimal(time),
        teleports=teleports,
        created_on=datetime(2026, 1, 1, tzinfo=UTC),
        updated_on=datetime(2026, 1, 1, tzinfo=UTC),
        updated_by=steamid64,
        is_valid=True,
    )
    db.add(record)
    await db.commit()
    await crud.rebuild_record_pbs(session=db)
    await db.commit()
    await db.refresh(record)
    return record


async def test_get_pb_records_tie_break_prefers_lower_globalapi_id(
    db: AsyncSession,
) -> None:
    player_id = random_steamid64()
    await _create_player(db, steamid64=player_id, name="Tie Runner")
    await _create_map(db, id=981000, name="kz_tie_break")
    await _create_server(db, id=981100, name="Tie Server")

    winner = await _create_record(
        db,
        id=981200,
        steamid64=player_id,
        map_id=981000,
        server_id=981100,
        mode_id=200,
        stage=0,
        time="12.345",
        teleports=0,
    )
    await _create_record(
        db,
        id=981201,
        steamid64=player_id,
        map_id=981000,
        server_id=981100,
        mode_id=201,
        stage=0,
        time="12.345",
        teleports=0,
    )

    records = await crud.get_pb_records(
        db,
        map_id=981000,
        stage=0,
        steamid64=None,
        scope=RecordScope.OVR,
        is_pro_only=False,
    )

    assert [record.id for record in records] == [winner.id]


async def test_get_max_record_globalapi_id_ignores_null_ids(
    db: AsyncSession,
) -> None:
    player_id = random_steamid64()
    await _create_player(db, steamid64=player_id, name="Max Runner")
    await _create_map(db, id=981001, name="kz_max_id")
    await _create_server(db, id=981101, name="Max Server")

    await _create_record(
        db,
        id=981210,
        steamid64=player_id,
        map_id=981001,
        server_id=981101,
        mode_id=200,
        stage=0,
        time="20.000",
        teleports=0,
    )
    await _create_record(
        db,
        id=None,
        steamid64=player_id,
        map_id=981001,
        server_id=981101,
        mode_id=200,
        stage=1,
        time="21.000",
        teleports=0,
    )

    assert await crud.get_max_record_globalapi_id(session=db) == 981210
