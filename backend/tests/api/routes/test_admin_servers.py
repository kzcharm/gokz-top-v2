import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import (
    Server,
    ServerGlobalapi,
    ServerGroup,
    ServerGroupCreate,
    ServerGroupStatus,
    ServerGroupUpdate,
)
from app.services import globalapi_server_sync
from tests.utils.server import create_server, create_server_group
from tests.utils.user import authentication_token_from_steamid
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


async def _create_globalapi_server(
    db: AsyncSession,
    *,
    id: int,
    owner_steamid64: int,
    approval_status: int = 1,
    group_id: uuid.UUID | None = None,
) -> ServerGlobalapi:
    server = ServerGlobalapi(
        id=id,
        group_id=group_id,
        port=27015,
        ip=f"203.0.113.{id % 255}",
        name=f"Admin Test Server {id}",
        owner_steamid64=owner_steamid64,
        approval_status=approval_status,
        approved_by_steamid64=0,
        created_at=datetime(2021, 1, 1, tzinfo=UTC),
        updated_at=datetime(2021, 1, 2, tzinfo=UTC),
        synced_at=datetime(2021, 1, 3, tzinfo=UTC),
    )
    db.add(server)
    await db.commit()
    await db.refresh(server)
    return server


async def test_admin_server_access_requires_approved_globalapi_server(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )
    await _create_globalapi_server(
        db,
        id=970001,
        owner_steamid64=steamid64,
        approval_status=0,
    )

    response = await client.get(
        f"{settings.API_V1_STR}/admin/servers/access",
        headers=headers,
    )

    assert response.status_code == 403

    await _create_globalapi_server(
        db,
        id=970002,
        owner_steamid64=steamid64,
        approval_status=1,
    )

    response = await client.get(
        f"{settings.API_V1_STR}/admin/servers/access",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["role"] == "server_owner"
    assert response.json()["can_approve_servers"] is False


async def test_admin_globalapi_owner_is_filtered_and_cannot_approve(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    owner_steamid64 = random_steamid64()
    other_steamid64 = random_steamid64()
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=owner_steamid64,
        db=db,
    )
    owned = await _create_globalapi_server(
        db,
        id=970010,
        owner_steamid64=owner_steamid64,
        approval_status=1,
    )
    await _create_globalapi_server(
        db,
        id=970011,
        owner_steamid64=other_steamid64,
        approval_status=1,
    )

    response = await client.get(
        f"{settings.API_V1_STR}/admin/servers/globalapi",
        headers=headers,
        params={"limit": 100},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["data"][0]["id"] == owned.id

    approve_response = await client.patch(
        f"{settings.API_V1_STR}/admin/servers/globalapi/{owned.id}",
        headers=headers,
        json={"approval_status": 0},
    )

    assert approve_response.status_code == 403


async def test_admin_globalapi_root_can_toggle_approval(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    server = await _create_globalapi_server(
        db,
        id=970020,
        owner_steamid64=random_steamid64(),
        approval_status=0,
    )

    response = await client.patch(
        f"{settings.API_V1_STR}/admin/servers/globalapi/{server.id}",
        headers=superuser_token_headers,
        json={"approval_status": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["approval_status"] == 1
    assert payload["approved_by_steamid64"] == str(settings.SUPER_USER_STEAMID64)

    refreshed = await db.get(ServerGlobalapi, server.id)
    assert refreshed is not None
    assert refreshed.approval_status == 1
    assert refreshed.approved_by_steamid64 == settings.SUPER_USER_STEAMID64


async def test_admin_globalapi_group_assignment_requires_owned_group(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    owner_steamid64 = random_steamid64()
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=owner_steamid64,
        db=db,
    )
    server = await _create_globalapi_server(
        db,
        id=970025,
        owner_steamid64=owner_steamid64,
        approval_status=1,
    )
    owned_group, _ = await create_server_group(db, owner_steamid64=owner_steamid64)
    other_group, _ = await create_server_group(db)

    forbidden_response = await client.patch(
        f"{settings.API_V1_STR}/admin/servers/globalapi/{server.id}",
        headers=headers,
        json={"group_id": str(other_group.id)},
    )
    assert forbidden_response.status_code == 403

    response = await client.patch(
        f"{settings.API_V1_STR}/admin/servers/globalapi/{server.id}",
        headers=headers,
        json={"group_id": str(owned_group.id)},
    )

    assert response.status_code == 200
    assert response.json()["group_id"] == str(owned_group.id)
    refreshed = await db.get(ServerGlobalapi, server.id)
    assert refreshed is not None
    assert refreshed.group_id == owned_group.id


async def test_admin_globalapi_root_rejects_missing_group(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    server = await _create_globalapi_server(
        db,
        id=970026,
        owner_steamid64=random_steamid64(),
        approval_status=1,
    )

    response = await client.patch(
        f"{settings.API_V1_STR}/admin/servers/globalapi/{server.id}",
        headers=superuser_token_headers,
        json={"group_id": str(uuid.uuid4())},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Server group not found"


async def test_admin_public_servers_owner_uses_group_only_ownership(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    owner_steamid64 = random_steamid64()
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=owner_steamid64,
        db=db,
    )
    await _create_globalapi_server(
        db,
        id=970030,
        owner_steamid64=owner_steamid64,
        approval_status=1,
    )
    owned_group, _ = await create_server_group(db, owner_steamid64=owner_steamid64)
    other_group, _ = await create_server_group(db)
    owned_server = await create_server(db, group_id=owned_group.id)
    await create_server(db, group_id=other_group.id)
    await create_server(db, group_id=None)

    response = await client.get(
        f"{settings.API_V1_STR}/admin/servers/public",
        headers=headers,
        params={"limit": 100},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["data"][0]["id"] == str(owned_server.id)

    clear_group_response = await client.patch(
        f"{settings.API_V1_STR}/admin/servers/public/{owned_server.id}",
        headers=headers,
        json={"group_id": None},
    )
    assert clear_group_response.status_code == 403

    owned_group_response = await client.get(
        f"{settings.API_V1_STR}/admin/servers/public",
        headers=headers,
        params={"limit": 100, "group_id": str(owned_group.id)},
    )
    assert owned_group_response.status_code == 200
    assert owned_group_response.json()["count"] == 1

    other_group_response = await client.get(
        f"{settings.API_V1_STR}/admin/servers/public",
        headers=headers,
        params={"limit": 100, "group_id": str(other_group.id)},
    )
    assert other_group_response.status_code == 200
    assert other_group_response.json()["count"] == 0


async def test_admin_public_server_owner_update_and_delete_access(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    owner_steamid64 = random_steamid64()
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=owner_steamid64,
        db=db,
    )
    await _create_globalapi_server(
        db,
        id=970035,
        owner_steamid64=owner_steamid64,
        approval_status=1,
    )
    owned_group, _ = await create_server_group(db, owner_steamid64=owner_steamid64)
    other_group, _ = await create_server_group(db)
    owned_server = await create_server(db, group_id=owned_group.id)
    other_server = await create_server(db, group_id=other_group.id)

    update_response = await client.patch(
        f"{settings.API_V1_STR}/admin/servers/public/{owned_server.id}",
        headers=headers,
        json={"city": "Cologne", "country": "DE"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["city"] == "Cologne"

    forbidden_update_response = await client.patch(
        f"{settings.API_V1_STR}/admin/servers/public/{owned_server.id}",
        headers=headers,
        json={"group_id": str(other_group.id)},
    )
    assert forbidden_update_response.status_code == 403

    forbidden_delete_response = await client.delete(
        f"{settings.API_V1_STR}/admin/servers/public/{other_server.id}",
        headers=headers,
    )
    assert forbidden_delete_response.status_code == 403

    delete_response = await client.delete(
        f"{settings.API_V1_STR}/admin/servers/public/{owned_server.id}",
        headers=headers,
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["message"] == "Server deleted successfully"
    assert await db.get(Server, owned_server.id) is None


async def test_admin_server_groups_owner_scope_and_metadata_update(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    owner_steamid64 = random_steamid64()
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=owner_steamid64,
        db=db,
    )
    await _create_globalapi_server(
        db,
        id=970036,
        owner_steamid64=owner_steamid64,
        approval_status=1,
    )
    owned_group, _ = await create_server_group(db, owner_steamid64=owner_steamid64)
    other_group, _ = await create_server_group(db)

    list_response = await client.get(
        f"{settings.API_V1_STR}/admin/servers/groups",
        headers=headers,
    )
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["count"] == 1
    assert payload["data"][0]["id"] == str(owned_group.id)
    assert payload["data"][0]["api_key"]

    ignored_status_response = await client.patch(
        f"{settings.API_V1_STR}/admin/servers/groups/{owned_group.id}",
        headers=headers,
        json={"status": ServerGroupStatus.INVALIDATED},
    )
    assert ignored_status_response.status_code == 200
    refreshed_group = await db.get(ServerGroup, owned_group.id)
    assert refreshed_group is not None
    assert refreshed_group.status == owned_group.status

    update_response = await client.patch(
        f"{settings.API_V1_STR}/admin/servers/groups/{owned_group.id}",
        headers=headers,
        json={
            "name": "Renamed Owner Group",
            "website": " https://example.com ",
            "discord": " ",
            "steam_group": " steamcommunity.com/groups/example ",
        },
    )
    assert update_response.status_code == 200
    updated_payload = update_response.json()
    assert updated_payload["name"] == "Renamed Owner Group"
    assert updated_payload["website"] == "https://example.com"
    assert updated_payload["discord"] is None
    assert updated_payload["steam_group"] == "steamcommunity.com/groups/example"

    rotate_response = await client.put(
        f"{settings.API_V1_STR}/admin/servers/groups/{owned_group.id}/api-key",
        headers=headers,
    )
    assert rotate_response.status_code == 200
    assert rotate_response.json()["api_key"]

    forbidden_group_response = await client.patch(
        f"{settings.API_V1_STR}/admin/servers/groups/{other_group.id}",
        headers=headers,
        json={"name": "Should Not Update"},
    )
    assert forbidden_group_response.status_code == 403


async def test_admin_server_group_custom_id_validation_and_delete_conflict(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    create_response = await client.post(
        f"{settings.API_V1_STR}/admin/servers/groups",
        headers=superuser_token_headers,
        json={"name": "Managed Group", "custom_id": " Managed_Group "},
    )
    assert create_response.status_code == 200
    group_id = create_response.json()["group"]["id"]
    assert create_response.json()["group"]["custom_id"] == "managed_group"
    assert create_response.json()["group"]["status"] == ServerGroupStatus.VALIDATED

    duplicate_response = await client.post(
        f"{settings.API_V1_STR}/admin/servers/groups",
        headers=superuser_token_headers,
        json={"name": "Other Group", "custom_id": "managed_group"},
    )
    assert duplicate_response.status_code == 409

    invalid_response = await client.post(
        f"{settings.API_V1_STR}/admin/servers/groups",
        headers=superuser_token_headers,
        json={"name": "Invalid Group", "custom_id": "1234"},
    )
    assert invalid_response.status_code == 422

    await create_server(db, group_id=uuid.UUID(group_id))
    await _create_globalapi_server(
        db,
        id=970037,
        owner_steamid64=settings.SUPER_USER_STEAMID64,
        approval_status=1,
        group_id=uuid.UUID(group_id),
    )
    delete_response = await client.delete(
        f"{settings.API_V1_STR}/admin/servers/groups/{group_id}",
        headers=superuser_token_headers,
    )

    assert delete_response.status_code == 409
    detail = delete_response.json()["detail"]
    assert detail["dependencies"]["servers"] == 1
    assert detail["dependencies"]["globalapi_servers"] == 1


async def test_server_group_models_normalize_metadata() -> None:
    group_in = ServerGroupCreate(
        name="Metadata Group",
        custom_id=" Managed_Group ",
        website=" ",
        discord=" https://discord.gg/example ",
        steam_group=" steamcommunity.com/groups/example ",
    )

    assert group_in.custom_id == "managed_group"
    assert group_in.website is None
    assert group_in.discord == "https://discord.gg/example"
    assert group_in.steam_group == "steamcommunity.com/groups/example"

    update_in = ServerGroupUpdate(custom_id=None, website=" https://example.com ")
    assert update_in.custom_id is None
    assert update_in.website == "https://example.com"

    with pytest.raises(ValueError, match="must contain at least one letter"):
        ServerGroupCreate(name="Invalid Group", custom_id="1234")


async def test_globalapi_server_sync_preserves_local_approval(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = await _create_globalapi_server(
        db,
        id=970040,
        owner_steamid64=random_steamid64(),
        approval_status=1,
    )
    server.approved_by_steamid64 = 76561198000000001
    db.add(server)
    await db.commit()

    async def _fake_fetch_servers_from_globalapi(
        *,
        approval_status: int,
        client: object | None = None,
    ) -> list[dict[str, object]]:
        del client
        if approval_status == 0:
            return [
                {
                    "id": server.id,
                    "port": server.port,
                    "ip": server.ip,
                    "name": server.name,
                    "owner_steamid64": server.owner_steamid64,
                    "approved_by_steamid64": 0,
                    "created_on": server.created_at.isoformat(),
                    "updated_on": server.updated_at.isoformat(),
                }
            ]
        return []

    monkeypatch.setattr(
        globalapi_server_sync,
        "fetch_servers_from_globalapi",
        _fake_fetch_servers_from_globalapi,
    )

    result = await globalapi_server_sync.sync_servers_from_globalapi(session=db)

    assert result.updated == 0
    refreshed = await db.get(ServerGlobalapi, server.id)
    assert refreshed is not None
    assert refreshed.approval_status == 1
    assert refreshed.approved_by_steamid64 == 76561198000000001
