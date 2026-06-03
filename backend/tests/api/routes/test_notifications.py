from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import Player
from tests.utils.utils import get_user_token_headers, random_steamid64


async def _create_player(
    *,
    db: AsyncSession,
    steamid64: int,
    name: str,
) -> Player:
    player = Player(
        steamid64=steamid64,
        name=name,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.add(player)
    await db.commit()
    await db.refresh(player)
    return player


@pytest.mark.asyncio
async def test_social_notifications_and_read_state(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    actor = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Notification Actor",
    )
    target = await _create_player(
        db=db,
        steamid64=random_steamid64(),
        name="Notification Target",
    )
    actor_headers = await get_user_token_headers(client, actor.steamid64)
    target_headers = await get_user_token_headers(client, target.steamid64)

    await client.post(
        f"{settings.API_V1_STR}/players/{target.steamid64}/likes",
        headers=actor_headers,
    )
    await client.post(
        f"{settings.API_V1_STR}/players/{target.steamid64}/likes",
        headers=actor_headers,
    )
    await client.post(
        f"{settings.API_V1_STR}/players/{target.steamid64}/comments",
        headers=actor_headers,
        json={"text": "  nice profile  "},
    )
    await client.put(
        f"{settings.API_V1_STR}/player-follows/players/{target.steamid64}",
        headers=actor_headers,
    )

    notifications_response = await client.get(
        f"{settings.API_V1_STR}/me/notifications",
        headers=target_headers,
    )
    assert notifications_response.status_code == 200
    notifications_payload = notifications_response.json()
    assert notifications_payload["count"] == 3
    assert [item["type"] for item in notifications_payload["data"]] == [
        "player_follow",
        "profile_comment",
        "profile_like",
    ]
    assert notifications_payload["data"][0]["actor"]["steamid64"] == str(
        actor.steamid64
    )
    assert notifications_payload["data"][1]["comment_preview"] == "nice profile"

    unread_response = await client.get(
        f"{settings.API_V1_STR}/me/notifications/unread-count",
        headers=target_headers,
    )
    assert unread_response.status_code == 200
    assert unread_response.json()["unread_count"] == 3

    first_notification_id = notifications_payload["data"][0]["id"]
    mark_read_response = await client.patch(
        f"{settings.API_V1_STR}/me/notifications/{first_notification_id}/read",
        headers=target_headers,
    )
    assert mark_read_response.status_code == 200
    assert mark_read_response.json()["read_at"] is not None

    unread_after_one_response = await client.get(
        f"{settings.API_V1_STR}/me/notifications/unread-count",
        headers=target_headers,
    )
    assert unread_after_one_response.json()["unread_count"] == 2

    mark_all_response = await client.patch(
        f"{settings.API_V1_STR}/me/notifications/read-all",
        headers=target_headers,
    )
    assert mark_all_response.status_code == 200

    unread_after_all_response = await client.get(
        f"{settings.API_V1_STR}/me/notifications/unread-count",
        headers=target_headers,
    )
    assert unread_after_all_response.json()["unread_count"] == 0


@pytest.mark.asyncio
async def test_notifications_require_authentication(client: AsyncClient) -> None:
    response = await client.get(f"{settings.API_V1_STR}/me/notifications")

    assert response.status_code == 401
