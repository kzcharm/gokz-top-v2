import uuid

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import ServerGroup
from tests.utils.server import create_server, create_server_group

pytestmark = pytest.mark.asyncio


async def test_read_server_groups_public_returns_counts(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    group, _ = await create_server_group(db, name="Public Group")
    await create_server(db, group_id=group.id)

    response = await client.get(f"{settings.API_V1_STR}/server-groups/")

    assert response.status_code == 200
    payload = response.json()
    matching = next(item for item in payload["data"] if item["id"] == str(group.id))
    assert matching["name"] == "Public Group"
    assert matching["server_count"] == 1


async def test_create_server_group_requires_superuser(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    response = await client.post(
        f"{settings.API_V1_STR}/server-groups/",
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
        f"{settings.API_V1_STR}/server-groups/",
        headers=superuser_token_headers,
        json={"name": "Managed Group"},
    )

    assert create_response.status_code == 200
    created_payload = create_response.json()
    group_id = created_payload["group"]["id"]
    original_api_key = created_payload["api_key"]

    rotate_response = await client.put(
        f"{settings.API_V1_STR}/server-groups/{group_id}/api-key",
        headers=superuser_token_headers,
    )

    assert rotate_response.status_code == 200
    rotated_payload = rotate_response.json()
    assert rotated_payload["group"]["id"] == group_id
    assert rotated_payload["api_key"] != original_api_key
    assert rotated_payload["group"]["api_key_prefix"] == rotated_payload["api_key"][:12]

    refreshed_group = await db.get(ServerGroup, uuid.UUID(group_id))
    assert refreshed_group is not None
    assert refreshed_group.api_key_prefix == rotated_payload["group"]["api_key_prefix"]
