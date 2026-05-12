import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.v1 import players as players_routes
from app.core.config import settings
from app.models import PlayerWebhook
from tests.utils.user import authentication_token_from_steamid
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


async def test_current_player_webhooks_crud_and_toggle(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )

    create_response = await client.post(
        f"{settings.API_V1_STR}/players/me/webhooks",
        headers=headers,
        json={
            "url": (
                "https://discord.com/api/webhooks/123456789012345678/"
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            )
        },
    )

    assert create_response.status_code == 200
    created_payload = create_response.json()
    assert created_payload["count"] == 1
    webhook_id = created_payload["data"][0]["id"]
    assert created_payload["data"][0]["provider"] == "discord"
    assert created_payload["data"][0]["enabled"] is True

    list_response = await client.get(
        f"{settings.API_V1_STR}/players/me/webhooks",
        headers=headers,
    )
    assert list_response.status_code == 200
    assert list_response.json()["count"] == 1

    update_response = await client.patch(
        f"{settings.API_V1_STR}/players/me/webhooks/{webhook_id}",
        headers=headers,
        json={"enabled": False},
    )
    assert update_response.status_code == 200
    assert update_response.json()["data"][0]["enabled"] is False

    delete_response = await client.delete(
        f"{settings.API_V1_STR}/players/me/webhooks/{webhook_id}",
        headers=headers,
    )
    assert delete_response.status_code == 200
    assert delete_response.json() == {"data": [], "count": 0}


async def test_current_player_webhooks_reject_invalid_url(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )

    response = await client.post(
        f"{settings.API_V1_STR}/players/me/webhooks",
        headers=headers,
        json={"url": "https://example.com/not-a-discord-webhook"},
    )

    assert response.status_code == 422
    assert (
        response.json()["detail"][0]["msg"]
        == "Value error, Webhook URL must use the Discord-compatible "
        "/api/webhooks/<id>/<token> format"
    )


async def test_current_player_webhooks_accept_discord_compatible_host(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )

    response = await client.post(
        f"{settings.API_V1_STR}/players/me/webhooks",
        headers=headers,
        json={
            "url": (
                "https://qqbot.axekz.com/api/webhooks/188099455/"
                "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
            )
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert (
        payload["data"][0]["url"]
        == "https://qqbot.axekz.com/api/webhooks/188099455/"
        "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
    )


async def test_current_player_webhooks_hide_other_users_webhooks(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    first_headers = await authentication_token_from_steamid(
        client=client,
        steamid64=random_steamid64(),
        db=db,
    )
    second_headers = await authentication_token_from_steamid(
        client=client,
        steamid64=random_steamid64(),
        db=db,
    )

    create_response = await client.post(
        f"{settings.API_V1_STR}/players/me/webhooks",
        headers=first_headers,
        json={
            "url": (
                "https://discord.com/api/webhooks/223456789012345678/"
                "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
            )
        },
    )
    webhook_id = create_response.json()["data"][0]["id"]

    for method in ("PATCH", "DELETE", "POST"):
        path = f"{settings.API_V1_STR}/players/me/webhooks/{webhook_id}"
        if method == "POST":
            path = f"{path}/test"
        response = await client.request(
            method,
            path,
            headers=second_headers,
            json={"enabled": False} if method == "PATCH" else None,
        )
        assert response.status_code == 404


async def test_current_player_webhook_test_updates_last_tested_at(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steamid64 = random_steamid64()
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )

    create_response = await client.post(
        f"{settings.API_V1_STR}/players/me/webhooks",
        headers=headers,
        json={
            "url": (
                "https://discord.com/api/webhooks/323456789012345678/"
                "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
            )
        },
    )
    webhook_id = create_response.json()["data"][0]["id"]

    async def _fake_send(*, webhook_url: str, payload: dict[str, object]) -> None:
        assert webhook_url.startswith("https://discord.com/api/webhooks/")
        assert "embeds" in payload

    monkeypatch.setattr(players_routes, "send_discord_webhook", _fake_send)

    response = await client.post(
        f"{settings.API_V1_STR}/players/me/webhooks/{webhook_id}/test",
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == webhook_id
    assert payload["last_tested_at"] is not None

    webhook = await db.get(PlayerWebhook, webhook_id)
    assert webhook is not None
    assert webhook.last_tested_at is not None


async def test_current_player_webhook_test_returns_502_on_delivery_failure(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steamid64 = random_steamid64()
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )

    create_response = await client.post(
        f"{settings.API_V1_STR}/players/me/webhooks",
        headers=headers,
        json={
            "url": (
                "https://discord.com/api/webhooks/423456789012345678/"
                "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
            )
        },
    )
    webhook_id = create_response.json()["data"][0]["id"]

    async def _failing_send(*, webhook_url: str, payload: dict[str, object]) -> None:
        del webhook_url, payload
        raise players_routes.httpx.ConnectError("network down")

    monkeypatch.setattr(players_routes, "send_discord_webhook", _failing_send)

    response = await client.post(
        f"{settings.API_V1_STR}/players/me/webhooks/{webhook_id}/test",
        headers=headers,
    )

    assert response.status_code == 502
    assert "Failed to send webhook" in response.json()["detail"]

    webhook = await db.get(PlayerWebhook, webhook_id)
    assert webhook is not None
    assert webhook.last_tested_at is None
