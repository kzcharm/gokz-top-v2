import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.services.qq_binding import QQ_BIND_TOKEN_PREFIX, QQ_BIND_TOKEN_SUFFIX_LENGTH
from tests.utils.user import authentication_token_from_steamid
from tests.utils.utils import random_steamid64


@pytest.mark.asyncio
async def test_create_current_player_qq_binding_code_returns_code(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "QQ_BIND_TOKEN_SECRET", "qq-secret")
    steamid64 = random_steamid64()
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )

    response = await client.post(
        f"{settings.API_V1_STR}/me/qq-binding-code",
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"].startswith(QQ_BIND_TOKEN_PREFIX)
    assert len(payload["code"]) == len(QQ_BIND_TOKEN_PREFIX) + QQ_BIND_TOKEN_SUFFIX_LENGTH
    assert payload["code"].isalnum()
    assert "expires_at" in payload


@pytest.mark.asyncio
async def test_create_current_player_qq_binding_code_requires_auth(
    client: AsyncClient,
) -> None:
    response = await client.post(f"{settings.API_V1_STR}/me/qq-binding-code")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_current_player_qq_binding_code_is_repeatable_for_same_user(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "QQ_BIND_TOKEN_SECRET", "qq-secret")
    steamid64 = random_steamid64()
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )

    first_response = await client.post(
        f"{settings.API_V1_STR}/me/qq-binding-code",
        headers=headers,
    )
    second_response = await client.post(
        f"{settings.API_V1_STR}/me/qq-binding-code",
        headers=headers,
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["code"] == second_response.json()["code"]


@pytest.mark.asyncio
async def test_create_current_player_qq_binding_code_returns_503_without_secret(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "QQ_BIND_TOKEN_SECRET", None)
    steamid64 = random_steamid64()
    headers = await authentication_token_from_steamid(
        client=client,
        steamid64=steamid64,
        db=db,
    )

    response = await client.post(
        f"{settings.API_V1_STR}/me/qq-binding-code",
        headers=headers,
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "QQ binding code generation is not configured"
