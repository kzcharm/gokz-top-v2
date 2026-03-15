from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlmodel import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import ServerGlobalapi

pytestmark = pytest.mark.asyncio


async def _create_server_globalapi(
    db: AsyncSession,
    *,
    id: int,
    port: int,
    ip: str,
    name: str,
    owner_steamid64: int,
    approval_status: int,
    approved_by_steamid64: int,
) -> ServerGlobalapi:
    await db.exec(delete(ServerGlobalapi).where(ServerGlobalapi.id == id))
    await db.commit()

    server = ServerGlobalapi(
        id=id,
        port=port,
        ip=ip,
        name=name,
        owner_steamid64=owner_steamid64,
        approval_status=approval_status,
        approved_by_steamid64=approved_by_steamid64,
        created_on=datetime(2021, 1, 1, tzinfo=UTC),
        updated_on=datetime(2021, 1, 2, tzinfo=UTC),
        synced_at=datetime(2021, 1, 3, tzinfo=UTC),
    )
    db.add(server)
    await db.commit()
    await db.refresh(server)
    return server


async def test_read_servers_v0_contract(client: AsyncClient, db: AsyncSession) -> None:
    await _create_server_globalapi(
        db,
        id=940100,
        port=27015,
        ip="203.0.113.10",
        name="Approved Server",
        owner_steamid64=76561198000000010,
        approval_status=1,
        approved_by_steamid64=76561198000000020,
    )

    response = await client.get("/v0/servers", params={"id": 940100, "limit": 10000})

    assert response.status_code == 200
    payload = response.json()
    assert payload == [
        {
            "id": 940100,
            "port": 27015,
            "ip": "203.0.113.10",
            "name": "Approved Server",
            "owner_steamid64": "76561198000000010",
        }
    ]


async def test_read_servers_v0_filters(client: AsyncClient, db: AsyncSession) -> None:
    await _create_server_globalapi(
        db,
        id=940110,
        port=39110,
        ip="203.0.113.11",
        name="ztest-alpha-kz-940110",
        owner_steamid64=76561198000000110,
        approval_status=1,
        approved_by_steamid64=76561198000000210,
    )
    await _create_server_globalapi(
        db,
        id=940111,
        port=39111,
        ip="203.0.113.12",
        name="ztest-beta-climb-940111",
        owner_steamid64=76561198000000111,
        approval_status=0,
        approved_by_steamid64=0,
    )
    await _create_server_globalapi(
        db,
        id=940112,
        port=39112,
        ip="203.0.113.13",
        name="ztest-gamma-kz-940112",
        owner_steamid64=76561198000000112,
        approval_status=1,
        approved_by_steamid64=76561198000000212,
    )

    response = await client.get("/v0/servers", params={"port": 39111})
    assert [item["id"] for item in response.json()] == [940111]

    response = await client.get("/v0/servers", params={"ip": "203.0.113.13"})
    assert [item["id"] for item in response.json()] == [940112]

    response = await client.get("/v0/servers", params={"name": "ztest-kz-94011"})
    assert response.json() == []

    response = await client.get("/v0/servers", params={"name": "ztest-alpha-kz-940110"})
    assert [item["id"] for item in response.json()] == [940110]

    response = await client.get("/v0/servers", params={"name": "ztest-gamma-kz-940112"})
    assert [item["id"] for item in response.json()] == [940112]

    response = await client.get("/v0/servers", params={"name": "kz-94011"})
    assert [item["id"] for item in response.json()] == [940110, 940112]

    response = await client.get(
        "/v0/servers",
        params={"owner_steamid64": 76561198000000110},
    )
    assert [item["id"] for item in response.json()] == [940110]

    response = await client.get(
        "/v0/servers",
        params=[("id", 940110), ("id", 940111), ("id", 940112), ("approval_status", 0)],
    )
    assert [item["id"] for item in response.json()] == [940111]

    response = await client.get(
        "/v0/servers",
        params=[("id", 940110), ("id", 940112)],
    )
    assert [item["id"] for item in response.json()] == [940110, 940112]

    response = await client.get(
        "/v0/servers",
        params=[("id", 940110), ("id", 940111), ("id", 940112), ("offset", 1), ("limit", 1)],
    )
    assert [item["id"] for item in response.json()] == [940111]


async def test_read_servers_v0_by_name_returns_matches(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await _create_server_globalapi(
        db,
        id=940120,
        port=39120,
        ip="203.0.113.14",
        name="ztest-network-940120",
        owner_steamid64=76561198000000120,
        approval_status=1,
        approved_by_steamid64=1,
    )
    await _create_server_globalapi(
        db,
        id=940121,
        port=39121,
        ip="203.0.113.15",
        name="ztest-network-940121",
        owner_steamid64=76561198000000121,
        approval_status=0,
        approved_by_steamid64=0,
    )

    response = await client.get("/v0/servers/name/ztest-network-94012")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [940120, 940121]


async def test_read_server_v0_not_found(client: AsyncClient) -> None:
    response = await client.get("/v0/servers/999999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Server not found"}
