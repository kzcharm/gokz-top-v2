from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.api.v1 import discord_social_links as routes
from app.core import security
from app.core.config import settings
from app.models import Player
from app.services.discord_social_link_verification import (
    DISCORD_STATE_COOKIE,
    create_discord_state,
    decode_discord_state,
)
from tests.utils.user import authentication_token_from_steamid
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio
START = "/v1/player-social-links/me/social-links/discord/connection-requests"
CALLBACK = "/v1/social-link-verifications/discord/callback"
ACCOUNT_ID = "123456789012345678"


@pytest.fixture(autouse=True)
def discord_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DISCORD_CLIENT_ID", "discord-client")
    monkeypatch.setattr(settings, "DISCORD_CLIENT_SECRET", "discord-secret")


async def player_headers(
    client: AsyncClient, db: AsyncSession
) -> tuple[int, dict[str, str]]:
    steamid64 = random_steamid64()
    db.add(Player(steamid64=steamid64, name="Discord Player"))
    await db.commit()
    return steamid64, await authentication_token_from_steamid(
        client=client, db=db, steamid64=steamid64
    )


async def start(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(START, headers=headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    query = parse_qs(urlsplit(response.json()["authorization_url"]).query)
    assert query["scope"] == ["identify"]
    assert query["redirect_uri"] == [f"{settings.BACKEND_PUBLIC_URL}{CALLBACK}"]
    return query["state"][0]


def assert_result(response: httpx.Response, status: str) -> None:
    assert response.status_code == 303
    location = urlsplit(response.headers["location"])
    assert location.path == "/settings/social-links"
    assert location.netloc == urlsplit(settings.FRONTEND_HOST).netloc
    assert parse_qs(location.query)["discordVerification"] == [status]
    assert "Max-Age=0" in response.headers["set-cookie"]


async def test_start_requires_auth_and_configuration(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert (await client.post(START)).status_code == 401
    _, headers = await player_headers(client, db)
    monkeypatch.setattr(settings, "DISCORD_CLIENT_SECRET", None)
    response = await client.post(START, headers=headers)
    assert response.status_code == 503
    assert response.json()["detail"] == "Discord linking is not configured"


async def test_connect_disconnect_and_reconnect(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    steamid64, headers = await player_headers(client, db)
    calls = []

    async def fetch(*, code: str) -> str:
        calls.append(code)
        return ACCOUNT_ID

    monkeypatch.setattr(routes, "fetch_discord_account_identifier", fetch)
    state = await start(client, headers)
    assert decode_discord_state(state).steamid64 == steamid64
    response = await client.get(
        CALLBACK, params={"state": state, "code": "code"}, follow_redirects=False
    )
    assert_result(response, "success")
    links = await crud.list_player_social_links(session=db, player_steamid64=steamid64)
    assert len(links) == 1
    assert links[0].verified
    assert links[0].account_identifier == ACCOUNT_ID
    assert links[0].metadata_json is None
    assert (await client.post(START, headers=headers)).status_code == 409
    assert (
        await client.patch(
            f"/v1/player-social-links/me/social-links/{links[0].id}",
            headers=headers,
            json={"url": "https://github.com/test"},
        )
    ).status_code == 422
    assert (
        await client.delete(
            f"/v1/player-social-links/me/social-links/{links[0].id}", headers=headers
        )
    ).status_code == 200
    state = await start(client, headers)
    assert_result(
        await client.get(CALLBACK, params={"state": state, "code": "new-code"}),
        "success",
    )
    assert calls == ["code", "new-code"]


@pytest.mark.parametrize(
    "failure",
    [
        "missing-state",
        "tampered",
        "expired",
        "wrong-purpose",
        "missing-cookie",
        "wrong-cookie",
        "denied",
        "missing-code",
        "provider",
    ],
)
async def test_callback_failures_never_create_link(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    steamid64, headers = await player_headers(client, db)
    state = await start(client, headers)
    params = {"state": state, "code": "private-code"}
    if failure == "missing-state":
        params.pop("state")
    elif failure == "tampered":
        params["state"] = "invalid"
    elif failure in {"expired", "wrong-purpose"}:
        payload = decode_discord_state(state).model_dump()
        if failure == "expired":
            payload["exp"] = 1
        else:
            payload["purpose"] = "other"
        params["state"] = jwt.encode(
            payload, settings.SECRET_KEY, algorithm=security.ALGORITHM
        )
    elif failure in {"missing-cookie", "wrong-cookie"}:
        client.cookies.clear()
        if failure == "wrong-cookie":
            client.cookies.set(DISCORD_STATE_COOKIE, "different", path=CALLBACK)
    elif failure == "denied":
        params["error"] = "access_denied"
    elif failure == "missing-code":
        params.pop("code")

    async def fetch(*, code: str) -> str:
        assert code == "private-code"
        assert failure == "provider", (
            "Provider must not be called for an invalid callback"
        )
        raise httpx.ConnectError("private-token private-code")

    monkeypatch.setattr(routes, "fetch_discord_account_identifier", fetch)
    response = await client.get(CALLBACK, params=params)
    assert_result(response, "error")
    assert "private-" not in response.headers["location"]
    assert not await crud.list_player_social_links(
        session=db, player_steamid64=steamid64
    )


@pytest.mark.parametrize("owner_is_initiator", [True, False])
async def test_callback_handles_link_created_during_authorization(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    owner_is_initiator: bool,
) -> None:
    steamid64, headers = await player_headers(client, db)
    state = await start(client, headers)
    owner = steamid64
    if not owner_is_initiator:
        owner, _ = await player_headers(client, db)
    await crud.create_player_social_link(
        session=db,
        player_steamid64=owner,
        url=f"https://discord.com/users/{ACCOUNT_ID}",
        verified=True,
    )

    async def fetch(*, code: str) -> str:
        assert code == "code"
        return ACCOUNT_ID

    monkeypatch.setattr(routes, "fetch_discord_account_identifier", fetch)
    assert_result(
        await client.get(CALLBACK, params={"state": state, "code": "code"}), "error"
    )
    links = await crud.list_player_social_links(session=db, player_steamid64=owner)
    assert len(links) == 1


async def test_manual_discord_urls_and_platform_changes_rejected(
    client: AsyncClient, db: AsyncSession
) -> None:
    steamid64, headers = await player_headers(client, db)
    url = f"https://discord.com/users/{ACCOUNT_ID}"
    assert (
        await client.post(
            "/v1/player-social-links/me/social-links",
            headers=headers,
            json={"url": url},
        )
    ).status_code == 422
    link = await crud.create_player_social_link(
        session=db,
        player_steamid64=steamid64,
        url="https://github.com/test",
        verified=False,
    )
    assert (
        await client.patch(
            f"/v1/player-social-links/me/social-links/{link.id}",
            headers=headers,
            json={"url": url},
        )
    ).status_code == 422


async def test_state_without_nonce_rejected() -> None:
    with pytest.raises(ValueError):
        decode_discord_state(
            create_discord_state(steamid64=1, nonce="x" * 32) + "invalid"
        )


async def test_callback_rejects_non_ascii_nonce_cookie(
    client: AsyncClient, db: AsyncSession
) -> None:
    steamid64, headers = await player_headers(client, db)
    state = await start(client, headers)
    response = await client.get(
        CALLBACK,
        params={"state": state, "code": "code"},
        headers=[(b"cookie", b"discord_social_link_state=\xe9")],
    )
    assert_result(response, "error")
    assert not await crud.list_player_social_links(
        session=db, player_steamid64=steamid64
    )


async def test_callback_rejects_invalid_provider_identifier(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    steamid64, headers = await player_headers(client, db)
    state = await start(client, headers)

    async def fetch(*, code: str) -> str:
        assert code == "code"
        return "invalid-account-id"

    monkeypatch.setattr(routes, "fetch_discord_account_identifier", fetch)
    assert_result(
        await client.get(CALLBACK, params={"state": state, "code": "code"}), "error"
    )
    assert not await crud.list_player_social_links(
        session=db, player_steamid64=steamid64
    )
