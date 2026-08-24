import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.services.qq_binding import (
    QQ_BIND_TOKEN_PREFIX,
    QQ_BIND_TOKEN_SUFFIX_LENGTH,
    encrypt_qq_binding_secret,
)
from tests.utils.user import authentication_token_from_steamid


async def _configure_secret(session: AsyncSession) -> None:
    await crud.create_qq_binding_secret(
        session=session,
        encrypted_secret=encrypt_qq_binding_secret("qq-secret"),
    )


@pytest.mark.asyncio
async def test_create_current_player_qq_binding_code_returns_code(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _configure_secret(db)
    steamid64 = 76561198000000001
    headers = await authentication_token_from_steamid(
        client=client, steamid64=steamid64, db=db
    )
    response = await client.post(
        f"{settings.API_V1_STR}/me/qq-binding-code", headers=headers
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
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_current_player_qq_binding_code_is_repeatable_for_same_user(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _configure_secret(db)
    steamid64 = 76561198000000002
    headers = await authentication_token_from_steamid(
        client=client, steamid64=steamid64, db=db
    )
    first_response = await client.post(
        f"{settings.API_V1_STR}/me/qq-binding-code", headers=headers
    )
    second_response = await client.post(
        f"{settings.API_V1_STR}/me/qq-binding-code", headers=headers
    )
    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["code"] == second_response.json()["code"]


@pytest.mark.asyncio
async def test_create_current_player_qq_binding_code_returns_503_without_secret(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await authentication_token_from_steamid(
        client=client, steamid64=76561198000000003, db=db
    )
    response = await client.post(
        f"{settings.API_V1_STR}/me/qq-binding-code", headers=headers
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "QQ binding code generation is not configured"
