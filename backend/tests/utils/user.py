from fastapi.testclient import TestClient
from sqlmodel import Session

from app import crud
from app.core.config import settings
from app.models import User
from tests.utils.utils import get_user_token_headers, random_steamid64


def user_authentication_headers(
    *, client: TestClient, steamid64: int
) -> dict[str, str]:
    response = client.post(
        f"{settings.API_V1_STR}/private/auth/session",
        json={
            "steamid64": steamid64,
            "is_superuser": False,
            "is_active": True,
            "name": "Test User",
        },
    )
    payload = response.json()
    return {"Authorization": f"Bearer {payload['access_token']}"}


def create_random_user(db: Session) -> User:
    steamid64 = random_steamid64()
    return crud.get_or_create_user_from_steam(session=db, steamid64=steamid64)


def authentication_token_from_steamid(
    *, client: TestClient, steamid64: int, db: Session
) -> dict[str, str]:
    crud.get_or_create_user_from_steam(session=db, steamid64=steamid64)
    return get_user_token_headers(client=client, steamid64=steamid64)
