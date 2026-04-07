from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import User


def _build_callback_params(steamid64: int) -> dict[str, str]:
    return {
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.mode": "id_res",
        "openid.op_endpoint": "https://steamcommunity.com/openid/login",
        "openid.claimed_id": f"https://steamcommunity.com/openid/id/{steamid64}",
        "openid.identity": f"https://steamcommunity.com/openid/id/{steamid64}",
        "openid.return_to": f"http://testserver{settings.API_V1_STR}/login/steam/callback",
        "openid.response_nonce": "2026-02-27T00:00:00Zabcdef",
        "openid.assoc_handle": "1234567890",
        "openid.signed": "op_endpoint,claimed_id,identity,return_to,response_nonce,assoc_handle",
        "openid.sig": "fake-signature",
    }


@pytest.mark.asyncio
async def test_login_steam_redirect_has_openid_params(client: AsyncClient) -> None:
    response = await client.get(
        f"{settings.API_V1_STR}/login/steam",
        follow_redirects=False,
    )

    assert response.status_code in {302, 307}
    location = response.headers["location"]
    parsed = urlparse(location)
    params = parse_qs(parsed.query)

    expected_base = str(client.base_url).rstrip("/")
    expected_return_to = f"{expected_base}{settings.API_V1_STR}/login/steam/callback"

    assert parsed.scheme == "https"
    assert parsed.netloc == "steamcommunity.com"
    assert parsed.path == "/openid/login"
    assert params["openid.mode"] == ["checkid_setup"]
    assert params["openid.ns"] == ["http://specs.openid.net/auth/2.0"]
    assert params["openid.realm"] == [expected_base]
    assert params["openid.return_to"] == [expected_return_to]


@pytest.mark.asyncio
async def test_steam_callback_invalid_mode(client: AsyncClient) -> None:
    response = await client.get(
        f"{settings.API_V1_STR}/login/steam/callback",
        params={"openid.mode": "cancel"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid OpenID mode"


@pytest.mark.asyncio
async def test_steam_callback_missing_claimed_id(client: AsyncClient) -> None:
    response = await client.get(
        f"{settings.API_V1_STR}/login/steam/callback",
        params={"openid.mode": "id_res"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Missing OpenID claimed_id"


@pytest.mark.asyncio
async def test_steam_callback_invalid_steamid_format(client: AsyncClient) -> None:
    response = await client.get(
        f"{settings.API_V1_STR}/login/steam/callback",
        params={
            "openid.mode": "id_res",
            "openid.claimed_id": "https://steamcommunity.com/openid/id/not-a-number",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid Steam ID format"


@pytest.mark.asyncio
async def test_steam_callback_missing_signature(client: AsyncClient) -> None:
    steamid64 = 76561199099990000
    response = await client.get(
        f"{settings.API_V1_STR}/login/steam/callback",
        params={
            "openid.mode": "id_res",
            "openid.claimed_id": f"https://steamcommunity.com/openid/id/{steamid64}",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Missing OpenID signature"


@pytest.mark.asyncio
async def test_steam_callback_openid_verification_failure(client: AsyncClient) -> None:
    steamid64 = 76561199099990001
    params = _build_callback_params(steamid64)

    mocked_response = Mock()
    mocked_response.raise_for_status.return_value = None
    mocked_response.text = "is_valid:false"

    with patch(
        "app.api.v1.login.httpx.AsyncClient.post",
        new=AsyncMock(return_value=mocked_response),
    ):
        response = await client.get(
            f"{settings.API_V1_STR}/login/steam/callback",
            params=params,
            follow_redirects=False,
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "OpenID verification failed"


@pytest.mark.asyncio
async def test_steam_callback_success_creates_user_and_redirects(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steamid64 = 76561199099990002
    params = _build_callback_params(steamid64)

    mocked_response = Mock()
    mocked_response.raise_for_status.return_value = None
    mocked_response.text = "ns:http://specs.openid.net/auth/2.0\nis_valid:true"

    with patch(
        "app.api.v1.login.httpx.AsyncClient.post",
        new=AsyncMock(return_value=mocked_response),
    ):
        response = await client.get(
            f"{settings.API_V1_STR}/login/steam/callback",
            params=params,
            follow_redirects=False,
        )

    assert response.status_code in {302, 307}
    location = response.headers["location"]
    assert location.startswith(
        f"{settings.FRONTEND_HOST.rstrip('/')}/auth/callback#access_token="
    )
    token = location.split("#access_token=", maxsplit=1)[1]

    test_token_response = await client.post(
        f"{settings.API_V1_STR}/login/test-token",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert test_token_response.status_code == 200
    assert test_token_response.json()["steamid64"] == str(steamid64)

    user = (await db.exec(select(User).where(User.steamid64 == steamid64))).first()
    assert user is not None


@pytest.mark.asyncio
async def test_use_access_token(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
) -> None:
    response = await client.post(
        f"{settings.API_V1_STR}/login/test-token",
        headers=superuser_token_headers,
    )

    assert response.status_code == 200
    result = response.json()
    assert result["steamid64"] == str(settings.SUPER_USER_STEAMID64)
    assert result["is_superuser"] is True
    assert result["player"] is not None


@pytest.mark.asyncio
async def test_private_auth_session_route_not_registered_when_helpers_disabled() -> None:
    import importlib

    from app.api import main as api_main_module

    previous_setting = settings.ENABLE_TEST_AUTH_HELPERS
    settings.ENABLE_TEST_AUTH_HELPERS = False
    try:
        reloaded = importlib.reload(api_main_module)
        paths = {
            getattr(route, "path", None)
            for route in reloaded.api_router.routes
        }
        assert "/private/auth/session" not in paths
    finally:
        settings.ENABLE_TEST_AUTH_HELPERS = previous_setting
        importlib.reload(api_main_module)
