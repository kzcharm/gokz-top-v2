from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import crud
from app.core.config import settings
from app.models import User
from tests.utils.user import create_random_user, user_authentication_headers
from tests.utils.utils import random_steamid64


def test_get_users_superuser_me(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    response = client.get(
        f"{settings.API_V1_STR}/users/me", headers=superuser_token_headers
    )

    assert response.status_code == 200
    current_user = response.json()
    assert current_user["is_active"] is True
    assert current_user["is_superuser"] is True
    assert current_user["steamid64"] == str(settings.SUPER_USER_STEAMID64)
    assert current_user["last_visited_at"] is not None
    assert current_user["player"] is not None


def test_get_users_normal_user_me(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    response = client.get(
        f"{settings.API_V1_STR}/users/me",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200
    current_user = response.json()
    assert current_user["is_active"] is True
    assert current_user["is_superuser"] is False
    assert int(current_user["steamid64"]) > 0
    assert current_user["last_visited_at"] is not None


def test_retrieve_users_as_superuser(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    db: Session,
) -> None:
    crud.get_or_create_user_from_steam(session=db, steamid64=random_steamid64())
    crud.get_or_create_user_from_steam(session=db, steamid64=random_steamid64())

    response = client.get(
        f"{settings.API_V1_STR}/users/", headers=superuser_token_headers
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] >= 1
    assert len(payload["data"]) >= 1
    for user in payload["data"]:
        assert "steamid64" in user


def test_retrieve_users_without_privileges(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    response = client.get(
        f"{settings.API_V1_STR}/users/",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 403


def test_get_existing_user_as_superuser(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    db: Session,
) -> None:
    user = create_random_user(db)

    response = client.get(
        f"{settings.API_V1_STR}/users/{user.steamid64}",
        headers=superuser_token_headers,
    )

    assert response.status_code == 200
    api_user = response.json()
    assert api_user["steamid64"] == str(user.steamid64)


def test_get_non_existing_user_as_superuser(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    missing_steamid64 = random_steamid64()
    response = client.get(
        f"{settings.API_V1_STR}/users/{missing_steamid64}",
        headers=superuser_token_headers,
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "User not found"}


def test_get_existing_user_current_user(client: TestClient, db: Session) -> None:
    steamid64 = random_steamid64()
    user = crud.get_or_create_user_from_steam(session=db, steamid64=steamid64)
    headers = user_authentication_headers(client=client, steamid64=steamid64)

    response = client.get(
        f"{settings.API_V1_STR}/users/{user.steamid64}",
        headers=headers,
    )

    assert response.status_code == 200
    api_user = response.json()
    assert api_user["steamid64"] == str(steamid64)


def test_get_existing_user_permissions_error(
    db: Session,
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    other_user = create_random_user(db)

    response = client.get(
        f"{settings.API_V1_STR}/users/{other_user.steamid64}",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "The user doesn't have enough privileges"}


def test_get_non_existing_user_permissions_error(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    user_id = random_steamid64()

    response = client.get(
        f"{settings.API_V1_STR}/users/{user_id}",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "The user doesn't have enough privileges"}


def test_update_user(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    db: Session,
) -> None:
    user = create_random_user(db)

    response = client.patch(
        f"{settings.API_V1_STR}/users/{user.steamid64}",
        headers=superuser_token_headers,
        json={"is_superuser": True, "is_active": False},
    )

    assert response.status_code == 200
    updated_user = response.json()
    assert updated_user["is_superuser"] is True
    assert updated_user["is_active"] is False

    db.expire_all()
    refreshed = db.get(User, user.steamid64)
    assert refreshed is not None
    assert refreshed.is_superuser is True
    assert refreshed.is_active is False


def test_update_user_not_exists(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    missing_steamid64 = random_steamid64()
    response = client.patch(
        f"{settings.API_V1_STR}/users/{missing_steamid64}",
        headers=superuser_token_headers,
        json={"is_active": True},
    )

    assert response.status_code == 404
    assert (
        response.json()["detail"]
        == "The user with this id does not exist in the system"
    )


def test_delete_user_me(client: TestClient, db: Session) -> None:
    steamid64 = random_steamid64()
    user = crud.get_or_create_user_from_steam(session=db, steamid64=steamid64)
    headers = user_authentication_headers(client=client, steamid64=steamid64)

    response = client.delete(
        f"{settings.API_V1_STR}/users/me",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["message"] == "User deleted successfully"

    result = db.exec(select(User).where(User.steamid64 == user.steamid64)).first()
    assert result is None


def test_delete_user_me_as_superuser(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    response = client.delete(
        f"{settings.API_V1_STR}/users/me",
        headers=superuser_token_headers,
    )

    assert response.status_code == 403
    assert (
        response.json()["detail"] == "Super users are not allowed to delete themselves"
    )


def test_delete_user_super_user(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    db: Session,
) -> None:
    user = create_random_user(db)

    response = client.delete(
        f"{settings.API_V1_STR}/users/{user.steamid64}",
        headers=superuser_token_headers,
    )

    assert response.status_code == 200
    assert response.json()["message"] == "User deleted successfully"

    result = db.exec(select(User).where(User.steamid64 == user.steamid64)).first()
    assert result is None


def test_delete_user_not_found(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    missing_steamid64 = random_steamid64()
    response = client.delete(
        f"{settings.API_V1_STR}/users/{missing_steamid64}",
        headers=superuser_token_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


def test_delete_user_current_super_user_error(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    db: Session,
) -> None:
    super_user = db.exec(
        select(User).where(User.steamid64 == settings.SUPER_USER_STEAMID64)
    ).first()
    assert super_user is not None

    response = client.delete(
        f"{settings.API_V1_STR}/users/{super_user.steamid64}",
        headers=superuser_token_headers,
    )

    assert response.status_code == 403
    assert (
        response.json()["detail"] == "Super users are not allowed to delete themselves"
    )


def test_delete_user_without_privileges(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    db: Session,
) -> None:
    other_user = create_random_user(db)

    response = client.delete(
        f"{settings.API_V1_STR}/users/{other_user.steamid64}",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "The user doesn't have enough privileges"
