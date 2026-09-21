import gzip
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import (
    KZMode,
    Map,
    Player,
    Record,
    Server,
    ServerGlobalapi,
    ServerGroup,
    ServerGroupCreate,
    ServerGroupStatus,
    ServerGroupUpdate,
    UserRole,
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
    name: str | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> ServerGlobalapi:
    if await db.get(Player, owner_steamid64) is None:
        db.add(Player(steamid64=owner_steamid64, name=str(owner_steamid64)))
    server = ServerGlobalapi(
        id=id,
        group_id=group_id,
        port=27015,
        ip=f"203.0.113.{id % 255}",
        name=name or f"Admin Test Server {id}",
        owner_steamid64=owner_steamid64,
        approval_status=approval_status,
        approved_by_steamid64=None,
        created_at=created_at or datetime(2021, 1, 1, tzinfo=UTC),
        updated_at=updated_at or datetime(2021, 1, 2, tzinfo=UTC),
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


async def test_admin_server_access_accepts_explicit_server_owner_role(
    client: AsyncClient,
) -> None:
    steamid64 = random_steamid64()
    response = await client.post(
        f"{settings.API_V1_STR}/private/auth/session",
        json={
            "steamid64": steamid64,
            "roles": [UserRole.SERVER_OWNER.value],
            "is_active": True,
            "name": "Server Owner",
        },
    )
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}

    access_response = await client.get(
        f"{settings.API_V1_STR}/admin/servers/access",
        headers=headers,
    )

    assert access_response.status_code == 200
    assert access_response.json() == {
        "role": "server_owner",
        "can_approve_servers": False,
        "owned_group_count": 0,
    }


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


async def test_admin_globalapi_root_can_change_owner(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    original_owner_steamid64 = random_steamid64()
    new_owner_steamid64 = 76561199000000028
    server = await _create_globalapi_server(
        db,
        id=970028,
        owner_steamid64=original_owner_steamid64,
    )
    db.add(Player(steamid64=new_owner_steamid64, name="New Owner"))
    await db.commit()

    response = await client.patch(
        f"{settings.API_V1_STR}/admin/servers/globalapi/{server.id}",
        headers=superuser_token_headers,
        json={"owner_steamid64": str(new_owner_steamid64)},
    )

    assert response.status_code == 200
    assert response.json()["owner_steamid64"] == str(new_owner_steamid64)
    refreshed = await db.get(ServerGlobalapi, server.id)
    assert refreshed is not None
    assert refreshed.owner_steamid64 == new_owner_steamid64


async def test_admin_globalapi_server_owner_cannot_change_owner(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    owner_steamid64 = random_steamid64()
    new_owner_steamid64 = 76561199000000029
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=owner_steamid64,
        db=db,
    )
    server = await _create_globalapi_server(
        db,
        id=970029,
        owner_steamid64=owner_steamid64,
    )
    db.add(Player(steamid64=new_owner_steamid64, name="New Owner"))
    await db.commit()

    response = await client.patch(
        f"{settings.API_V1_STR}/admin/servers/globalapi/{server.id}",
        headers=headers,
        json={"owner_steamid64": str(new_owner_steamid64)},
    )

    assert response.status_code == 403


async def test_admin_globalapi_owner_can_update_server_name(
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
        id=970027,
        owner_steamid64=owner_steamid64,
        approval_status=1,
    )

    response = await client.patch(
        f"{settings.API_V1_STR}/admin/servers/globalapi/{server.id}",
        headers=headers,
        json={"name": "  Updated Server Name  "},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated Server Name"
    refreshed = await db.get(ServerGlobalapi, server.id)
    assert refreshed is not None
    assert refreshed.name == "Updated Server Name"


async def test_admin_globalapi_root_can_export_gokz_localdb_mysql_dump(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    owner_steamid64 = 76561199000000123
    server = await _create_globalapi_server(
        db,
        id=979028,
        owner_steamid64=owner_steamid64,
        approval_status=1,
        name="Export Server",
    )
    map_obj = Map(
        id=979028,
        name="kz_export_test",
        validated=True,
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        synced_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    created_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    db.add(map_obj)
    db.add(
        Record(
            id=979028,
            steamid64=owner_steamid64,
            server_id=server.id,
            mode=KZMode.KZT,
            map_id=map_obj.id,
            stage=1,
            time=Decimal("12.345"),
            teleports=4,
            created_at=created_at,
            updated_at=created_at,
        )
    )
    db.add(
        Record(
            id=979029,
            steamid64=owner_steamid64,
            server_id=server.id,
            mode=KZMode.VNL,
            map_id=map_obj.id,
            time=Decimal("22.000"),
            created_at=created_at,
            updated_at=created_at,
            is_valid=False,
        )
    )
    await db.commit()

    response = await client.get(
        f"{settings.API_V1_STR}/admin/servers/globalapi/records/export",
        headers=superuser_token_headers,
        params=[("server_id", server.id)],
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/gzip"
    assert response.headers["x-exported-record-count"] == "1"
    assert response.headers["x-skipped-record-count"] == "1"
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="gokz-localdb-records-979028.sql.gz"'
    )
    sql = gzip.decompress(response.content).decode()
    steamid32 = owner_steamid64 - 76561197960265728
    assert "INSERT IGNORE INTO `Players`" in sql
    assert "INSERT IGNORE INTO `Maps`" in sql
    assert "INSERT INTO `Times`" in sql
    assert f"({steamid32},'kz_export_test',1,2,0,12345,4,'2026-01-02 03:04:05')" in sql
    assert "Exported records: 1" in sql
    assert "Skipped records: 1" in sql


async def test_admin_globalapi_owner_cannot_export_another_servers_records(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    owner_steamid64 = random_steamid64()
    other_owner_steamid64 = random_steamid64()
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=owner_steamid64,
        db=db,
    )
    owned_server = await _create_globalapi_server(
        db,
        id=979029,
        owner_steamid64=owner_steamid64,
    )
    other_server = await _create_globalapi_server(
        db,
        id=979030,
        owner_steamid64=other_owner_steamid64,
    )

    response = await client.get(
        f"{settings.API_V1_STR}/admin/servers/globalapi/records/export",
        headers=headers,
        params=[
            ("server_id", owned_server.id),
            ("server_id", other_server.id),
        ],
    )

    assert response.status_code == 403


async def test_admin_globalapi_list_supports_filtering_and_sorting(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    owner_steamid64 = random_steamid64()
    await _create_globalapi_server(
        db,
        id=970021,
        owner_steamid64=owner_steamid64,
        approval_status=1,
        name="Charlie Server",
        created_at=datetime(2021, 1, 9, tzinfo=UTC),
        updated_at=datetime(2021, 1, 6, tzinfo=UTC),
    )
    await _create_globalapi_server(
        db,
        id=970022,
        owner_steamid64=owner_steamid64,
        approval_status=1,
        name="Alpha Server",
        created_at=datetime(2021, 1, 5, tzinfo=UTC),
        updated_at=datetime(2021, 1, 4, tzinfo=UTC),
    )
    await _create_globalapi_server(
        db,
        id=970023,
        owner_steamid64=owner_steamid64,
        approval_status=0,
        name="Bravo Server",
        created_at=datetime(2021, 1, 7, tzinfo=UTC),
        updated_at=datetime(2021, 1, 8, tzinfo=UTC),
    )

    default_response = await client.get(
        f"{settings.API_V1_STR}/admin/servers/globalapi",
        headers=superuser_token_headers,
        params={
            "limit": 100,
            "approval_status": 1,
            "owner_steamid64": owner_steamid64,
        },
    )
    assert default_response.status_code == 200
    default_payload = default_response.json()
    assert [server["id"] for server in default_payload["data"]] == [970022, 970021]
    assert default_payload["data"][0]["created_at"]

    id_search_response = await client.get(
        f"{settings.API_V1_STR}/admin/servers/globalapi",
        headers=superuser_token_headers,
        params={"q": "970022", "limit": 100},
    )
    assert id_search_response.status_code == 200
    assert [server["id"] for server in id_search_response.json()["data"]] == [970022]

    name_search_response = await client.get(
        f"{settings.API_V1_STR}/admin/servers/globalapi",
        headers=superuser_token_headers,
        params={"q": "Alpha", "limit": 100},
    )
    assert name_search_response.status_code == 200
    name_search_payload = name_search_response.json()
    assert 970022 in [server["id"] for server in name_search_payload["data"]]
    assert all(
        "alpha" in (server["name"] or "").lower()
        for server in name_search_payload["data"]
    )

    server_sort_response = await client.get(
        f"{settings.API_V1_STR}/admin/servers/globalapi",
        headers=superuser_token_headers,
        params={
            "limit": 100,
            "owner_steamid64": owner_steamid64,
            "sort_by": "server",
            "sort_order": "asc",
        },
    )
    assert server_sort_response.status_code == 200
    assert [server["id"] for server in server_sort_response.json()["data"]] == [
        970022,
        970023,
        970021,
    ]

    updated_sort_response = await client.get(
        f"{settings.API_V1_STR}/admin/servers/globalapi",
        headers=superuser_token_headers,
        params={
            "limit": 100,
            "owner_steamid64": owner_steamid64,
            "sort_by": "updated_at",
            "sort_order": "desc",
        },
    )
    assert updated_sort_response.status_code == 200
    assert [server["id"] for server in updated_sort_response.json()["data"]] == [
        970023,
        970021,
        970022,
    ]

    created_sort_response = await client.get(
        f"{settings.API_V1_STR}/admin/servers/globalapi",
        headers=superuser_token_headers,
        params={
            "limit": 100,
            "owner_steamid64": owner_steamid64,
            "sort_by": "created_at",
            "sort_order": "desc",
        },
    )
    assert created_sort_response.status_code == 200
    assert [server["id"] for server in created_sort_response.json()["data"]] == [
        970021,
        970023,
        970022,
    ]

    id_sort_response = await client.get(
        f"{settings.API_V1_STR}/admin/servers/globalapi",
        headers=superuser_token_headers,
        params={
            "limit": 100,
            "owner_steamid64": owner_steamid64,
            "sort_by": "id",
            "sort_order": "desc",
        },
    )
    assert id_sort_response.status_code == 200
    assert [server["id"] for server in id_sort_response.json()["data"]] == [
        970023,
        970022,
        970021,
    ]


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
    superuser_token_headers: dict[str, str],
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
        json={"city": "Cologne", "country": "DE", "is_public": False},
    )
    assert update_response.status_code == 200
    assert update_response.json()["city"] == "Cologne"
    assert update_response.json()["is_public"] is False

    hidden_response = await client.get(
        f"{settings.API_V1_STR}/admin/servers/public",
        headers=headers,
        params={"limit": 100, "is_public": False},
    )
    assert hidden_response.status_code == 200
    assert hidden_response.json()["count"] == 1
    assert hidden_response.json()["data"][0]["id"] == str(owned_server.id)

    forbidden_update_response = await client.patch(
        f"{settings.API_V1_STR}/admin/servers/public/{other_server.id}",
        headers=headers,
        json={"is_public": False},
    )
    assert forbidden_update_response.status_code == 403

    root_update_response = await client.patch(
        f"{settings.API_V1_STR}/admin/servers/public/{other_server.id}",
        headers=superuser_token_headers,
        json={"is_public": False},
    )
    assert root_update_response.status_code == 200
    assert root_update_response.json()["is_public"] is False

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
    superuser_token_headers: dict[str, str],
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
    assert payload["data"][0]["last_api_key_used_at"] is None

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

    forbidden_owner_update = await client.patch(
        f"{settings.API_V1_STR}/admin/servers/groups/{owned_group.id}",
        headers=headers,
        json={"owner_steamid64": None},
    )
    assert forbidden_owner_update.status_code == 403

    new_owner_steamid64 = 76561198000099999
    db.add(Player(steamid64=new_owner_steamid64, name="New Group Owner"))
    await db.commit()
    owner_update_response = await client.patch(
        f"{settings.API_V1_STR}/admin/servers/groups/{other_group.id}",
        headers=superuser_token_headers,
        json={"owner_steamid64": str(new_owner_steamid64)},
    )
    assert owner_update_response.status_code == 200
    assert owner_update_response.json()["owner_steamid64"] == str(new_owner_steamid64)
    await db.refresh(other_group)
    assert other_group.owner_steamid64 == new_owner_steamid64


async def test_admin_server_groups_support_backend_sorting_and_pagination(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    alpha, _ = await create_server_group(db, name="Alpha")
    beta, _ = await create_server_group(db, name="Beta")
    gamma, _ = await create_server_group(db, name="Gamma")

    alpha.last_api_key_used_at = None
    alpha.created_at = datetime(2026, 9, 3, tzinfo=UTC)
    alpha.updated_at = datetime(2026, 9, 1, tzinfo=UTC)
    beta.last_api_key_used_at = datetime(2026, 9, 3, tzinfo=UTC)
    beta.created_at = datetime(2026, 9, 1, tzinfo=UTC)
    beta.updated_at = datetime(2026, 9, 2, tzinfo=UTC)
    gamma.last_api_key_used_at = datetime(2026, 9, 1, tzinfo=UTC)
    gamma.created_at = datetime(2026, 9, 2, tzinfo=UTC)
    gamma.updated_at = datetime(2026, 9, 3, tzinfo=UTC)
    db.add_all([alpha, beta, gamma])
    await db.commit()

    expected_orders = {
        ("name", "asc"): ["Alpha", "Beta", "Gamma"],
        ("name", "desc"): ["Gamma", "Beta", "Alpha"],
        ("last_api_key_used_at", "asc"): ["Gamma", "Beta", "Alpha"],
        ("last_api_key_used_at", "desc"): ["Beta", "Gamma", "Alpha"],
        ("created_at", "asc"): ["Beta", "Gamma", "Alpha"],
        ("created_at", "desc"): ["Alpha", "Gamma", "Beta"],
        ("updated_at", "asc"): ["Alpha", "Beta", "Gamma"],
        ("updated_at", "desc"): ["Gamma", "Beta", "Alpha"],
    }
    for (sort_by, sort_order), expected_names in expected_orders.items():
        response = await client.get(
            f"{settings.API_V1_STR}/admin/servers/groups",
            headers=superuser_token_headers,
            params={"sort_by": sort_by, "sort_order": sort_order},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["count"] == 3
        assert [group["name"] for group in payload["data"]] == expected_names

    paginated_response = await client.get(
        f"{settings.API_V1_STR}/admin/servers/groups",
        headers=superuser_token_headers,
        params={
            "offset": 1,
            "limit": 1,
            "sort_by": "name",
            "sort_order": "asc",
        },
    )
    assert paginated_response.status_code == 200
    assert paginated_response.json()["count"] == 3
    assert [group["name"] for group in paginated_response.json()["data"]] == ["Beta"]


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

    update_in = ServerGroupUpdate(website=" https://example.com ")
    assert update_in.custom_id is None
    assert update_in.website == "https://example.com"

    with pytest.raises(ValueError, match="must contain at least one English letter"):
        ServerGroupCreate(name="Invalid Group", custom_id="1234")

    with pytest.raises(ValueError, match="custom_id is required"):
        ServerGroupUpdate(custom_id=None)


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
    db.add(Player(steamid64=76561198000000001, name="Approver"))
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
