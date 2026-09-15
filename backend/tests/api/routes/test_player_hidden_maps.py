from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlmodel import col, delete, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.models import Map, Player, PlayerHiddenMap, Record, RecordPb, ServerGlobalapi
from tests.utils.user import authentication_token_from_steamid
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


async def _create_player(db: AsyncSession, *, steamid64: int, name: str) -> None:
    await db.exec(delete(Player).where(col(Player.steamid64) == steamid64))
    await db.commit()
    db.add(Player(steamid64=steamid64, name=name))
    await db.commit()


async def _create_map(db: AsyncSession, *, map_id: int) -> None:
    await db.exec(delete(Map).where(col(Map.id) == map_id))
    await db.commit()
    db.add(
        Map(
            id=map_id,
            name=f"kz_hidden_{map_id}",
            filesize=1,
            validated=True,
            difficulty=4,
            approved_by_steamid64=76561198003275951,
        )
    )
    await db.commit()


async def test_hidden_maps_are_private_and_idempotent(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    owner_steamid64 = random_steamid64()
    other_steamid64 = random_steamid64()
    map_id = 984000
    await _create_player(db, steamid64=owner_steamid64, name="Hidden Maps Owner")
    await _create_player(db, steamid64=other_steamid64, name="Other Player")
    await _create_map(db, map_id=map_id)
    owner_headers = await authentication_token_from_steamid(
        client=client,
        steamid64=owner_steamid64,
        db=db,
    )
    other_headers = await authentication_token_from_steamid(
        client=client,
        steamid64=other_steamid64,
        db=db,
    )

    for _ in range(2):
        response = await client.post(
            f"{settings.API_V1_STR}/me/hidden-maps",
            headers=owner_headers,
            json={"map_id": map_id},
        )
        assert response.status_code == 200
        assert response.json()["count"] == 1

    owner_response = await client.get(
        f"{settings.API_V1_STR}/me/hidden-maps", headers=owner_headers
    )
    assert owner_response.status_code == 200
    assert owner_response.json()["data"][0]["map_id"] == map_id

    other_response = await client.get(
        f"{settings.API_V1_STR}/me/hidden-maps", headers=other_headers
    )
    assert other_response.status_code == 200
    assert other_response.json() == {"data": [], "count": 0}

    count = int(
        (
            await db.exec(
                select(func.count()).select_from(PlayerHiddenMap).where(
                    PlayerHiddenMap.player_steamid64 == owner_steamid64
                )
            )
        ).one()
    )
    assert count == 1

    delete_response = await client.delete(
        f"{settings.API_V1_STR}/me/hidden-maps/{map_id}", headers=owner_headers
    )
    assert delete_response.status_code == 200
    assert delete_response.json() == {"data": [], "count": 0}

    repeated_delete = await client.delete(
        f"{settings.API_V1_STR}/me/hidden-maps/{map_id}", headers=owner_headers
    )
    assert repeated_delete.status_code == 200
    assert repeated_delete.json() == {"data": [], "count": 0}

    await client.post(
        f"{settings.API_V1_STR}/me/hidden-maps",
        headers=owner_headers,
        json={"map_id": map_id},
    )
    await db.exec(delete(Map).where(col(Map.id) == map_id))
    await db.commit()
    assert int((await db.exec(select(func.count()).select_from(PlayerHiddenMap))).one()) == 0


async def test_hidden_maps_require_auth_and_preserve_record_data(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    map_id = 984001
    server_id = 984001
    await _create_player(db, steamid64=steamid64, name="Rating Runner")
    await _create_map(db, map_id=map_id)
    for player_steamid64 in (76561198000000010, 76561198000000020):
        if await db.get(Player, player_steamid64) is None:
            db.add(Player(steamid64=player_steamid64, name=str(player_steamid64)))
    db.add(
        ServerGlobalapi(
            id=server_id,
            port=27015,
            ip="203.0.113.42",
            name="Hidden Maps Server",
            owner_steamid64=76561198000000010,
            approval_status=1,
            approved_by_steamid64=76561198000000020,
        )
    )
    await db.commit()
    record, _created, _updated = await crud.upsert_record(
        session=db,
        record_id=984001,
        record_uuid=None,
        steamid64=steamid64,
        server_id=server_id,
        mode_id=200,
        map_id=map_id,
        stage=0,
        time_seconds=Decimal("20"),
        teleports=1,
        points=900,
        created_on=datetime(2026, 9, 15, tzinfo=UTC),
        updated_on=datetime(2026, 9, 15, tzinfo=UTC),
        updated_by=steamid64,
        replay_id=None,
        is_valid=True,
    )
    await db.commit()

    unauthenticated = await client.get(f"{settings.API_V1_STR}/me/hidden-maps")
    assert unauthenticated.status_code == 401

    headers = await authentication_token_from_steamid(
        client=client, steamid64=steamid64, db=db
    )
    response = await client.post(
        f"{settings.API_V1_STR}/me/hidden-maps",
        headers=headers,
        json={"map_id": map_id},
    )
    assert response.status_code == 200
    assert (await db.exec(select(Record).where(Record.id == record.id))).first() is not None
    assert (
        await db.exec(select(RecordPb).where(RecordPb.record_uuid == record.uuid))
    ).first() is not None
