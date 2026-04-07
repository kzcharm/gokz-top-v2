from datetime import UTC, datetime

import pytest
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import ServerGlobalapi
from app.services.globalapi_server_sync import (
    SERVER_DATETIME_FALLBACK,
    _normalize_datetime,
    sync_servers_from_globalapi,
)
from tests.utils.server import create_server_group

pytestmark = pytest.mark.asyncio


async def test_sync_servers_from_globalapi_upserts_and_infers_approval_status(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing_id = 941000
    unchanged_id = 941004
    new_id = 941001
    duplicate_id = 941002
    stale_id = 941003

    await db.exec(
        delete(ServerGlobalapi).where(
            ServerGlobalapi.id.in_(
                [existing_id, unchanged_id, new_id, duplicate_id, stale_id]
            )
        )
    )
    await db.commit()

    group, _ = await create_server_group(db, name="mirrored-group")
    group_id = group.id
    existing_server = ServerGlobalapi(
        id=existing_id,
        group_id=group_id,
        port=27015,
        ip="198.51.100.10",
        name="Existing Replica",
        owner_steamid64=76561198000001000,
        approval_status=0,
        approved_by_steamid64=0,
        created_on=datetime(2020, 1, 1, tzinfo=UTC),
        updated_on=datetime(2020, 1, 1, tzinfo=UTC),
        synced_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    stale_server = ServerGlobalapi(
        id=stale_id,
        port=27016,
        ip="198.51.100.13",
        name="Historical Replica",
        owner_steamid64=76561198000001003,
        approval_status=0,
        approved_by_steamid64=0,
        created_on=datetime(2020, 1, 1, tzinfo=UTC),
        updated_on=datetime(2020, 1, 1, tzinfo=UTC),
        synced_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    unchanged_server = ServerGlobalapi(
        id=unchanged_id,
        port=27021,
        ip="198.51.100.21",
        name="Approval Unchanged",
        owner_steamid64=76561198000001004,
        approval_status=1,
        approved_by_steamid64=0,
        created_on=datetime(2020, 1, 2, tzinfo=UTC),
        updated_on=datetime(2020, 1, 2, tzinfo=UTC),
        synced_at=datetime(2020, 1, 2, tzinfo=UTC),
    )
    db.add(existing_server)
    db.add(stale_server)
    db.add(unchanged_server)
    await db.commit()

    async def _mock_fetch(*, approval_status: int, client: object | None = None) -> list[dict[str, object]]:
        del client
        if approval_status == 0:
            return [
                {
                    "id": duplicate_id,
                    "port": 27017,
                    "ip": "198.51.100.17",
                    "name": "Duplicate Unapproved",
                    "owner_steamid64": "76561198000001002",
                    "approved_by_steamid64": "0",
                    "created_on": "bad",
                    "updated_on": None,
                    "approval_status": 1,
                },
                {"id": "bad-id"},
            ]
        return [
            {
                "id": existing_id,
                "port": 27018,
                "ip": "198.51.100.18",
                "name": "Existing Approved",
                "owner_steamid64": "76561198000001000",
                "approved_by_steamid64": "76561198000009999",
                "created_on": "0001-01-01T00:00:00",
                "updated_on": "2024-06-01T12:00:00",
            },
            {
                "id": new_id,
                "port": 27019,
                "ip": "198.51.100.19",
                "name": "New Approved",
                "owner_steamid64": "76561198000001001",
                "approved_by_steamid64": "76561198000009998",
                "created_on": "2024-06-02T12:00:00",
                "updated_on": "2024-06-03T12:00:00",
            },
            {
                "id": unchanged_id,
                "port": 27022,
                "ip": "198.51.100.22",
                "name": "Changed Upstream But Ignore",
                "owner_steamid64": "76561198000001999",
                "approved_by_steamid64": "76561198000009996",
                "created_on": "2024-06-06T12:00:00",
                "updated_on": "2024-06-07T12:00:00",
            },
            {
                "id": duplicate_id,
                "port": 27020,
                "ip": "198.51.100.20",
                "name": "Duplicate Approved",
                "owner_steamid64": "76561198000001002",
                "approved_by_steamid64": "76561198000009997",
                "created_on": "2024-06-04T12:00:00",
                "updated_on": "2024-06-05T12:00:00",
            },
        ]

    monkeypatch.setattr(
        "app.services.globalapi_server_sync.fetch_servers_from_globalapi",
        _mock_fetch,
    )

    result = await sync_servers_from_globalapi(session=db)

    assert result.processed == 6
    assert result.created == 2
    assert result.updated == 1
    assert result.errors == 1
    assert result.warnings == 1

    refreshed_existing = (
        await db.exec(
            select(
                ServerGlobalapi.group_id,
                ServerGlobalapi.approval_status,
                ServerGlobalapi.name,
                ServerGlobalapi.created_on,
                ServerGlobalapi.updated_on,
                ServerGlobalapi.synced_at,
            ).where(ServerGlobalapi.id == existing_id)
        )
    ).one()
    assert refreshed_existing[0] == group_id
    assert refreshed_existing[1] == 1
    assert refreshed_existing[2] == "Existing Replica"
    assert refreshed_existing[3] == datetime(2020, 1, 1, tzinfo=UTC)
    assert refreshed_existing[4] == datetime(2020, 1, 1, tzinfo=UTC)
    assert refreshed_existing[5] == datetime(2020, 1, 1, tzinfo=UTC)

    refreshed_new = (
        await db.exec(
            select(ServerGlobalapi.approval_status, ServerGlobalapi.name).where(
                ServerGlobalapi.id == new_id
            )
        )
    ).one()
    assert refreshed_new == (1, "New Approved")

    refreshed_duplicate = (
        await db.exec(
            select(ServerGlobalapi.approval_status, ServerGlobalapi.name).where(
                ServerGlobalapi.id == duplicate_id
            )
        )
    ).one()
    assert refreshed_duplicate == (1, "Duplicate Approved")

    refreshed_stale = (
        await db.exec(
            select(ServerGlobalapi.name).where(ServerGlobalapi.id == stale_id)
        )
    ).one()
    assert refreshed_stale == "Historical Replica"

    refreshed_unchanged = (
        await db.exec(
            select(
                ServerGlobalapi.approval_status,
                ServerGlobalapi.port,
                ServerGlobalapi.ip,
                ServerGlobalapi.name,
                ServerGlobalapi.owner_steamid64,
                ServerGlobalapi.synced_at,
            ).where(ServerGlobalapi.id == unchanged_id)
        )
    ).one()
    assert refreshed_unchanged == (
        1,
        27021,
        "198.51.100.21",
        "Approval Unchanged",
        76561198000001004,
        datetime(2020, 1, 2, tzinfo=UTC),
    )


async def test_normalize_server_datetime_fallback() -> None:
    fallback = _normalize_datetime(SERVER_DATETIME_FALLBACK)

    assert _normalize_datetime(None) == fallback
    assert _normalize_datetime("bad-value") == fallback
    assert _normalize_datetime("0001-01-01T00:00:00") == fallback
