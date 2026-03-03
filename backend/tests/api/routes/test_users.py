import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.models import User
from tests.utils.user import create_random_user, user_authentication_headers
from tests.utils.utils import random_steamid64


@pytest.mark.asyncio
async def test_get_users_superuser_me(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
) -> None:
    response = await client.get(
        f"{settings.API_V1_STR}/users/me", headers=superuser_token_headers
    )

    assert response.status_code == 200
    current_user = response.json()
    assert current_user["is_active"] is True
    assert current_user["is_superuser"] is True
    assert current_user["steamid64"] == str(settings.SUPER_USER_STEAMID64)
    assert current_user["last_visited_at"] is not None
    assert current_user["player"] is not None


@pytest.mark.asyncio
async def test_get_users_normal_user_me(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    response = await client.get(
        f"{settings.API_V1_STR}/users/me",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200
    current_user = response.json()
    assert current_user["is_active"] is True
    assert current_user["is_superuser"] is False
    assert int(current_user["steamid64"]) > 0
    assert current_user["last_visited_at"] is not None


@pytest.mark.asyncio
async def test_retrieve_users_as_superuser(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    await crud.get_or_create_user_from_steam(session=db, steamid64=random_steamid64())
    await crud.get_or_create_user_from_steam(session=db, steamid64=random_steamid64())

    response = await client.get(
        f"{settings.API_V1_STR}/users/",
        headers=superuser_token_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] >= 1
    assert len(payload["data"]) >= 1
    for user in payload["data"]:
        assert "steamid64" in user


@pytest.mark.asyncio
async def test_retrieve_users_without_privileges(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    response = await client.get(
        f"{settings.API_V1_STR}/users/",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_existing_user_as_superuser(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    user = await create_random_user(db)

    response = await client.get(
        f"{settings.API_V1_STR}/users/{user.steamid64}",
        headers=superuser_token_headers,
    )

    assert response.status_code == 200
    api_user = response.json()
    assert api_user["steamid64"] == str(user.steamid64)


@pytest.mark.asyncio
async def test_get_non_existing_user_as_superuser(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
) -> None:
    missing_steamid64 = random_steamid64()
    response = await client.get(
        f"{settings.API_V1_STR}/users/{missing_steamid64}",
        headers=superuser_token_headers,
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "User not found"}


@pytest.mark.asyncio
async def test_get_existing_user_current_user(
    client: AsyncClient, db: AsyncSession
) -> None:
    steamid64 = random_steamid64()
    user = await crud.get_or_create_user_from_steam(session=db, steamid64=steamid64)
    headers = await user_authentication_headers(client=client, steamid64=steamid64)

    response = await client.get(
        f"{settings.API_V1_STR}/users/{user.steamid64}",
        headers=headers,
    )

    assert response.status_code == 200
    api_user = response.json()
    assert api_user["steamid64"] == str(steamid64)


@pytest.mark.asyncio
async def test_get_existing_user_permissions_error(
    db: AsyncSession,
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    other_user = await create_random_user(db)

    response = await client.get(
        f"{settings.API_V1_STR}/users/{other_user.steamid64}",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "The user doesn't have enough privileges"}


@pytest.mark.asyncio
async def test_get_non_existing_user_permissions_error(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    user_id = random_steamid64()

    response = await client.get(
        f"{settings.API_V1_STR}/users/{user_id}",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "The user doesn't have enough privileges"}


@pytest.mark.asyncio
async def test_update_user(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    user = await create_random_user(db)
    steamid64 = user.steamid64

    response = await client.patch(
        f"{settings.API_V1_STR}/users/{steamid64}",
        headers=superuser_token_headers,
        json={"is_superuser": True, "is_active": False},
    )

    assert response.status_code == 200
    updated_user = response.json()
    assert updated_user["is_superuser"] is True
    assert updated_user["is_active"] is False

    db.expire_all()
    refreshed = (await db.exec(select(User).where(User.steamid64 == steamid64))).first()
    assert refreshed is not None
    assert refreshed.is_superuser is True
    assert refreshed.is_active is False


@pytest.mark.asyncio
async def test_update_user_not_exists(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
) -> None:
    missing_steamid64 = random_steamid64()
    response = await client.patch(
        f"{settings.API_V1_STR}/users/{missing_steamid64}",
        headers=superuser_token_headers,
        json={"is_active": True},
    )

    assert response.status_code == 404
    assert (
        response.json()["detail"]
        == "The user with this id does not exist in the system"
    )


@pytest.mark.asyncio
async def test_delete_user_me(client: AsyncClient, db: AsyncSession) -> None:
    steamid64 = random_steamid64()
    user = await crud.get_or_create_user_from_steam(session=db, steamid64=steamid64)
    headers = await user_authentication_headers(client=client, steamid64=steamid64)

    response = await client.delete(
        f"{settings.API_V1_STR}/users/me",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["message"] == "User deleted successfully"

    result = (
        await db.exec(select(User).where(User.steamid64 == user.steamid64))
    ).first()
    assert result is None


@pytest.mark.asyncio
async def test_delete_user_me_as_superuser(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
) -> None:
    response = await client.delete(
        f"{settings.API_V1_STR}/users/me",
        headers=superuser_token_headers,
    )

    assert response.status_code == 403
    assert (
        response.json()["detail"] == "Super users are not allowed to delete themselves"
    )


@pytest.mark.asyncio
async def test_delete_user_super_user(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    user = await create_random_user(db)

    response = await client.delete(
        f"{settings.API_V1_STR}/users/{user.steamid64}",
        headers=superuser_token_headers,
    )

    assert response.status_code == 200
    assert response.json()["message"] == "User deleted successfully"

    result = (
        await db.exec(select(User).where(User.steamid64 == user.steamid64))
    ).first()
    assert result is None


@pytest.mark.asyncio
async def test_delete_user_not_found(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
) -> None:
    missing_steamid64 = random_steamid64()
    response = await client.delete(
        f"{settings.API_V1_STR}/users/{missing_steamid64}",
        headers=superuser_token_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


@pytest.mark.asyncio
async def test_delete_user_current_super_user_error(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    super_user = (
        await db.exec(
            select(User).where(User.steamid64 == settings.SUPER_USER_STEAMID64)
        )
    ).first()
    assert super_user is not None

    response = await client.delete(
        f"{settings.API_V1_STR}/users/{super_user.steamid64}",
        headers=superuser_token_headers,
    )

    assert response.status_code == 403
    assert (
        response.json()["detail"] == "Super users are not allowed to delete themselves"
    )


@pytest.mark.asyncio
async def test_delete_user_without_privileges(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    other_user = await create_random_user(db)

    response = await client.delete(
        f"{settings.API_V1_STR}/users/{other_user.steamid64}",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "The user doesn't have enough privileges"
