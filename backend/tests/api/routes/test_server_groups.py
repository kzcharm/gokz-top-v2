import uuid

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import ServerGroup, ServerGroupStatus
from tests.utils.server import create_server, create_server_group

pytestmark = pytest.mark.asyncio


async def test_read_server_groups_public_returns_counts(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    group, _ = await create_server_group(db, name="Public Group")
    await create_server(db, group_id=group.id)

    response = await client.get(f"{settings.API_V1_STR}/server-groups")

    assert response.status_code == 200
    payload = response.json()
    matching = next(item for item in payload["data"] if item["id"] == str(group.id))
    assert matching["name"] == "Public Group"
    assert matching["owner_steamid64"] == str(group.owner_steamid64)
    assert matching["status"] == group.status
    assert matching["server_count"] == 1
    assert "api_key_prefix" not in matching
    assert "api_key_created_at" not in matching


async def test_create_server_group_requires_superuser(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    response = await client.post(
        f"{settings.API_V1_STR}/server-groups",
        headers=normal_user_token_headers,
        json={"name": "Blocked Group"},
    )

    assert response.status_code == 403


async def test_create_and_rotate_server_group_api_key(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    create_response = await client.post(
        f"{settings.API_V1_STR}/server-groups",
        headers=superuser_token_headers,
        json={"name": "Managed Group"},
    )

    assert create_response.status_code == 200
    created_payload = create_response.json()
    group_id = created_payload["group"]["id"]
    original_api_key = created_payload["api_key"]
    assert created_payload["group"]["owner_steamid64"] == str(settings.SUPER_USER_STEAMID64)
    assert created_payload["group"]["status"] == ServerGroupStatus.PENDING

    rotate_response = await client.put(
        f"{settings.API_V1_STR}/server-groups/{group_id}/api-key",
        headers=superuser_token_headers,
    )

    assert rotate_response.status_code == 200
    rotated_payload = rotate_response.json()
    assert rotated_payload["group"]["id"] == group_id
    assert rotated_payload["api_key"] != original_api_key
    assert "api_key_prefix" not in rotated_payload["group"]
    assert "api_key_created_at" not in rotated_payload["group"]

    refreshed_group = await db.get(ServerGroup, uuid.UUID(group_id))
    assert refreshed_group is not None
    assert refreshed_group.api_key == rotated_payload["api_key"]
    assert refreshed_group.owner_steamid64 == settings.SUPER_USER_STEAMID64
    assert refreshed_group.status == ServerGroupStatus.PENDING


async def test_invalidated_owner_cannot_create_another_server_group(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
) -> None:
    create_response = await client.post(
        f"{settings.API_V1_STR}/server-groups",
        headers=superuser_token_headers,
        json={"name": "First Group"},
    )
    group_id = create_response.json()["group"]["id"]

    invalidate_response = await client.patch(
        f"{settings.API_V1_STR}/server-groups/{group_id}",
        headers=superuser_token_headers,
        json={"status": ServerGroupStatus.INVALIDATED},
    )
    assert invalidate_response.status_code == 200

    second_create_response = await client.post(
        f"{settings.API_V1_STR}/server-groups",
        headers=superuser_token_headers,
        json={"name": "Blocked Group"},
    )

    assert second_create_response.status_code == 403
    assert second_create_response.json()["detail"] == "Server group owner is permanently blocked"
