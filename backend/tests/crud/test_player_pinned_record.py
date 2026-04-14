from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.models import (
    Map,
    ModeScope,
    Player,
    PlayerPinnedRecord,
    Record,
    RecordPb,
    RecordType,
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
    time: str,
    teleports: int = 1,
) -> Record:
    record_uuid_subquery = select(Record.uuid).where(Record.id == id)
    await db.exec(delete(RecordPb).where(RecordPb.record_uuid.in_(record_uuid_subquery)))
    await db.exec(delete(Record).where(Record.id == id))
    await db.commit()
    record, _created, _updated = await crud.upsert_record(
        session=db,
        record_id=id,
        record_uuid=None,
        steamid64=steamid64,
        server_id=984000,
        mode_id=200,
        map_id=map_id,
        stage=0,
        time_seconds=Decimal(time),
        teleports=teleports,
        points=0,
        created_on=datetime(2026, 4, 1, tzinfo=UTC),
        updated_on=datetime(2026, 4, 1, tzinfo=UTC),
        updated_by=steamid64,
        replay_id=None,
        is_valid=True,
    )
    await db.commit()
    await db.refresh(record)
    return record


async def test_resolve_player_pinned_records_uses_current_pb(
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    await _create_player(db, steamid64=steamid64, name="Pinned Runner")
    await _create_map(db, id=984100, name="kz_pin_pb")
    await _create_server(db, id=984000, name="Pinned Server")

    await _create_record(
        db,
        id=984200,
        steamid64=steamid64,
        map_id=984100,
        time="20.000",
    )
    await crud.create_player_pinned_record(
        session=db,
        player_steamid64=steamid64,
        map_id=984100,
        scope=ModeScope.OVR,
        record_type=RecordType.NUB,
    )

    improved_record = await _create_record(
        db,
        id=984201,
        steamid64=steamid64,
        map_id=984100,
        time="19.000",
    )

    resolved = await crud.resolve_player_pinned_records_public(
        session=db,
        player_steamid64=steamid64,
        scope=ModeScope.OVR,
    )

    assert len(resolved) == 1
    assert str(resolved[0].record.uuid) == str(improved_record.uuid)


async def test_resolve_player_pinned_records_keeps_players_pb_not_map_wr(
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    other_steamid64 = random_steamid64()
    await _create_player(db, steamid64=steamid64, name="Pinned Runner")
    await _create_player(db, steamid64=other_steamid64, name="Faster Runner")
    await _create_map(db, id=984105, name="kz_pin_not_wr")
    await _create_server(db, id=984000, name="Pinned Server")

    player_record = await _create_record(
        db,
        id=984205,
        steamid64=steamid64,
        map_id=984105,
        time="20.000",
    )
    await _create_record(
        db,
        id=984206,
        steamid64=other_steamid64,
        map_id=984105,
        time="19.000",
    )
    await crud.create_player_pinned_record(
        session=db,
        player_steamid64=steamid64,
        map_id=984105,
        scope=ModeScope.OVR,
        record_type=RecordType.NUB,
    )

    resolved = await crud.resolve_player_pinned_records_public(
        session=db,
        player_steamid64=steamid64,
        scope=ModeScope.OVR,
    )

    assert len(resolved) == 1
    assert str(resolved[0].record.uuid) == str(player_record.uuid)
    assert resolved[0].record.player["steamid64"] == str(steamid64)


async def test_resolve_player_pinned_records_omits_targets_without_pb(
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    await _create_player(db, steamid64=steamid64, name="Pinned Runner")
    await _create_map(db, id=984110, name="kz_missing_pb")
    await _create_server(db, id=984000, name="Pinned Server")

    record = await _create_record(
        db,
        id=984210,
        steamid64=steamid64,
        map_id=984110,
        time="20.000",
    )
    await crud.create_player_pinned_record(
        session=db,
        player_steamid64=steamid64,
        map_id=984110,
        scope=ModeScope.OVR,
        record_type=RecordType.NUB,
    )

    await db.exec(delete(RecordPb).where(RecordPb.record_uuid == record.uuid))
    await db.commit()

    resolved = await crud.resolve_player_pinned_records_public(
        session=db,
        player_steamid64=steamid64,
        scope=ModeScope.OVR,
    )

    assert resolved == []

    stored = (
        await db.exec(
            select(PlayerPinnedRecord).where(PlayerPinnedRecord.player_steamid64 == steamid64)
        )
    ).all()
    assert len(stored) == 1
