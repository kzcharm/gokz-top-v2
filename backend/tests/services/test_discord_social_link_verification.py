import httpx
import pytest

from app.core.config import settings
from app.models import PlayerSocialPlatform
from app.services import discord_social_link_verification as discord
from app.services.player_social_links import (
    build_player_social_link_url,
    parse_player_social_link_url,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [None, "token-http", "token-missing", "user-http", "user-invalid", "user-json"],
)
async def test_discord_provider_exchange(
    monkeypatch: pytest.MonkeyPatch, failure: str | None
) -> None:
    monkeypatch.setattr(settings, "DISCORD_CLIENT_ID", "client-id")
    monkeypatch.setattr(settings, "DISCORD_CLIENT_SECRET", "client-secret")
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/token"):
            assert (
                request.headers["content-type"] == "application/x-www-form-urlencoded"
            )
            assert b"grant_type=authorization_code" in request.content
            assert b"client_secret=client-secret" in request.content
            if failure == "token-http":
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(
                200,
                json={}
                if failure == "token-missing"
                else {"access_token": "transient-token"},
            )
        assert str(request.url) == "https://discord.com/api/v10/users/@me"
        assert request.headers["authorization"] == "Bearer transient-token"
        if failure == "user-http":
            return httpx.Response(503)
        if failure == "user-json":
            return httpx.Response(200, text="invalid-json")
        return httpx.Response(
            200,
            json={
                "id": "not-an-id" if failure == "user-invalid" else "123456789012345678"
            },
        )

    client_class = httpx.AsyncClient
    monkeypatch.setattr(
        discord.httpx,
        "AsyncClient",
        lambda **kwargs: client_class(transport=httpx.MockTransport(handler), **kwargs),
    )
    if failure:
        with pytest.raises((ValueError, httpx.HTTPError)):
            await discord.fetch_discord_account_identifier(code="authorization-code")
    else:
        assert (
            await discord.fetch_discord_account_identifier(code="authorization-code")
            == "123456789012345678"
        )
        assert len(requests) == 2


@pytest.mark.parametrize(
    "url",
    [
        "https://discord.gg/invite",
        "https://discord.com/channels/123",
        "https://discord.com/users/name",
        "https://discord.com/users/0",
        "https://discord.com/users/18446744073709551616",
        "https://discord.com/users/123/extra",
    ],
)
def test_reject_invalid_discord_profiles(url: str) -> None:
    assert parse_player_social_link_url(url) is None


def test_discord_profile_round_trip() -> None:
    url = build_player_social_link_url(
        platform=PlayerSocialPlatform.DISCORD, account_identifier="123456789012345678"
    )
    parsed = parse_player_social_link_url(url)
    assert parsed is not None
    assert parsed.platform == PlayerSocialPlatform.DISCORD
    assert parsed.account_identifier == "123456789012345678"
