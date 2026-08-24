import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.services.qq_binding import create_qq_binding_code, verify_qq_binding_code
from tests.utils.user import authentication_token_from_steamid

QQ_SECRET_URL = f"{settings.API_V1_STR}/admin/settings/qq-binding-secret"


@pytest.mark.asyncio
async def test_superuser_manages_qq_binding_secret_lifecycle(
    client: AsyncClient,
    db: AsyncSession,
    superuser_token_headers: dict[str, str],
) -> None:
    status_response = await client.get(QQ_SECRET_URL, headers=superuser_token_headers)
    assert status_response.status_code == 200
    assert status_response.json() == {
        "configured": False,
        "created_at": None,
        "updated_at": None,
    }

    generated_response = await client.post(
        f"{QQ_SECRET_URL}/generate", headers=superuser_token_headers
    )
    assert generated_response.status_code == 200
    assert generated_response.headers["cache-control"] == "no-store"
    first_secret = generated_response.json()["secret"]
    stored_secret = await crud.get_qq_binding_secret(session=db)
    assert stored_secret is not None
    assert stored_secret.encrypted_secret != first_secret

    assert (
        await client.post(f"{QQ_SECRET_URL}/generate", headers=superuser_token_headers)
    ).status_code == 409
    reveal_response = await client.get(
        f"{QQ_SECRET_URL}/reveal", headers=superuser_token_headers
    )
    assert reveal_response.status_code == 200
    assert reveal_response.headers["cache-control"] == "no-store"
    assert reveal_response.json()["secret"] == first_secret

    code = (
        await create_qq_binding_code(session=db, steamid64="76561198000000001")
    ).code
    rotate_response = await client.post(
        f"{QQ_SECRET_URL}/rotate", headers=superuser_token_headers
    )
    assert rotate_response.status_code == 200
    assert rotate_response.json()["secret"] != first_secret
    with pytest.raises(ValueError, match="signature"):
        await verify_qq_binding_code(session=db, code=code)

    revoke_response = await client.delete(QQ_SECRET_URL, headers=superuser_token_headers)
    assert revoke_response.status_code == 204
    assert (await client.get(QQ_SECRET_URL, headers=superuser_token_headers)).json()[
        "configured"
    ] is False
    assert (
        await client.get(f"{QQ_SECRET_URL}/reveal", headers=superuser_token_headers)
    ).status_code == 404
    player_headers = await authentication_token_from_steamid(
        client=client, steamid64=76561198000000002, db=db
    )
    assert (
        await client.post(
            f"{settings.API_V1_STR}/me/qq-binding-code", headers=player_headers
        )
    ).status_code == 503


@pytest.mark.asyncio
async def test_qq_binding_secret_admin_api_requires_superuser(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await authentication_token_from_steamid(
        client=client, steamid64=76561198000000010, db=db
    )
    assert (await client.get(QQ_SECRET_URL, headers=headers)).status_code == 403
    assert (await client.post(f"{QQ_SECRET_URL}/generate", headers=headers)).status_code == 403
