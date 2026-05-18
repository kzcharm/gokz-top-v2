from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlmodel import delete, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.models import (
    Map,
    Player,
    PlayerPinnedRecord,
    Record,
    RecordPb,
    ServerGlobalapi,
)
from tests.utils.user import authentication_token_from_steamid
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
    mode_id: int = 200,
    teleports: int = 1,
    time: str = "20.000",
    created_on: datetime | None = None,
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
        server_id=server_id,
        mode_id=mode_id,
        map_id=map_id,
        stage=0,
        time_seconds=Decimal(time),
        teleports=teleports,
        points=0,
        created_on=created_on or datetime(2026, 4, 1, tzinfo=UTC),
        updated_on=created_on or datetime(2026, 4, 1, tzinfo=UTC),
        updated_by=steamid64,
        replay_id=None,
        is_valid=True,
    )
    await db.commit()
    await db.refresh(record)
    return record


async def _seed_player_records(
    db: AsyncSession,
    *,
    player_steamid64: int,
    map_ids: list[int],
) -> None:
    await _create_player(db, steamid64=player_steamid64, name="Pinned Runner")
    await _create_server(db, id=982000, name="Pinned Server")
    for index, map_id in enumerate(map_ids):
        await _create_map(db, id=map_id, name=f"kz_pinned_{map_id}")
        await _create_record(
            db,
            id=983000 + index,
            steamid64=player_steamid64,
            map_id=map_id,
            server_id=982000,
            time=f"{20 + index}.000",
            created_on=datetime(2026, 4, 1, tzinfo=UTC) + timedelta(minutes=index),
        )


async def test_player_pinned_records_owner_can_create_read_and_delete(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    await _seed_player_records(db, player_steamid64=steamid64, map_ids=[981000])
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )

    create_response = await client.post(
        f"{settings.API_V1_STR}/players/{steamid64}/pinned-records",
        headers=headers,
        json={
            "map_id": 981000,
            "scope": "OVR",
            "type": "NUB",
        },
    )

    assert create_response.status_code == 200
    create_payload = create_response.json()
    assert create_payload["count"] == 1
    assert create_payload["data"][0]["player_steamid64"] == str(steamid64)
    assert create_payload["data"][0]["map_id"] == 981000
    assert create_payload["data"][0]["scope"] == "OVR"
    assert create_payload["data"][0]["type"] == "NUB"
    assert create_payload["data"][0]["record"]["map_id"] == 981000
    assert create_payload["data"][0]["record"]["is_replay_available"] is False

    read_response = await client.get(
        f"{settings.API_V1_STR}/players/{steamid64}/pinned-records",
        params={"scope": "OVR"},
    )
    assert read_response.status_code == 200
    assert read_response.json()["count"] == 1

    delete_response = await client.delete(
        f"{settings.API_V1_STR}/players/{steamid64}/pinned-records",
        headers=headers,
        params={"map_id": 981000, "scope": "OVR", "type": "NUB"},
    )
    assert delete_response.status_code == 200
    assert delete_response.json() == {"data": [], "count": 0}


async def test_player_pinned_records_read_returns_players_pb_not_map_wr(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    other_steamid64 = random_steamid64()
    await _seed_player_records(db, player_steamid64=steamid64, map_ids=[981005])
    await _create_player(db, steamid64=other_steamid64, name="Faster Runner")
    await _create_record(
        db,
        id=983999,
        steamid64=other_steamid64,
        map_id=981005,
        server_id=982000,
        time="10.000",
    )
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )

    create_response = await client.post(
        f"{settings.API_V1_STR}/players/{steamid64}/pinned-records",
        headers=headers,
        json={
            "map_id": 981005,
            "scope": "OVR",
            "type": "NUB",
        },
    )

    assert create_response.status_code == 200
    payload = create_response.json()
    assert payload["count"] == 1
    assert payload["data"][0]["record"]["player"]["steamid64"] == str(steamid64)
    assert payload["data"][0]["record"]["time"] == 20.0


async def test_player_pinned_records_repin_is_idempotent(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    await _seed_player_records(db, player_steamid64=steamid64, map_ids=[981010])
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )

    for _ in range(2):
        response = await client.post(
            f"{settings.API_V1_STR}/players/{steamid64}/pinned-records",
            headers=headers,
            json={"map_id": 981010, "scope": "OVR", "type": "NUB"},
        )
        assert response.status_code == 200
        assert response.json()["count"] == 1

    statement = select(func.count()).select_from(PlayerPinnedRecord)
    count = int((await db.exec(statement)).one())
    assert count == 1


async def test_player_pinned_records_forbid_mutating_another_player(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    owner_steamid64 = random_steamid64()
    other_steamid64 = random_steamid64()
    await _seed_player_records(db, player_steamid64=owner_steamid64, map_ids=[981020])
    await _create_player(db, steamid64=other_steamid64, name="Other User")
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=other_steamid64,
        db=db,
    )

    response = await client.post(
        f"{settings.API_V1_STR}/players/{owner_steamid64}/pinned-records",
        headers=headers,
        json={"map_id": 981020, "scope": "OVR", "type": "NUB"},
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "You cannot modify another player's pinned records"
    }


async def test_player_pinned_records_seventh_pin_evicts_oldest_in_scope(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    map_ids = [981100 + index for index in range(7)]
    await _seed_player_records(db, player_steamid64=steamid64, map_ids=map_ids)
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )

    for map_id in map_ids:
        response = await client.post(
            f"{settings.API_V1_STR}/players/{steamid64}/pinned-records",
            headers=headers,
            json={"map_id": map_id, "scope": "OVR", "type": "NUB"},
        )
        assert response.status_code == 200

    read_response = await client.get(
        f"{settings.API_V1_STR}/players/{steamid64}/pinned-records",
        params={"scope": "OVR"},
    )
    assert read_response.status_code == 200
    payload = read_response.json()
    assert payload["count"] == 6
    assert [entry["map_id"] for entry in payload["data"]] == list(reversed(map_ids[1:]))


async def test_player_pinned_records_read_filters_to_requested_scope(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    await _seed_player_records(db, player_steamid64=steamid64, map_ids=[981200, 981201])
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )

    response_ovr = await client.post(
        f"{settings.API_V1_STR}/players/{steamid64}/pinned-records",
        headers=headers,
        json={"map_id": 981200, "scope": "OVR", "type": "NUB"},
    )
    assert response_ovr.status_code == 200

    read_response = await client.get(
        f"{settings.API_V1_STR}/players/{steamid64}/pinned-records",
        params={"scope": "SKZ"},
    )
    assert read_response.status_code == 200
    assert read_response.json() == {"data": [], "count": 0}
