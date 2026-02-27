import random
import string

from fastapi.testclient import TestClient

from app.core.config import settings


def random_lower_string() -> str:
    return "".join(random.choices(string.ascii_lowercase, k=32))


def random_steamid64() -> int:
    suffix = random.randint(1_000_000_000, 9_999_999_999)
    return int(f"76561{suffix}")


def _token_headers_from_private_session(
    client: TestClient, *, steamid64: int, is_superuser: bool = False
) -> dict[str, str]:
    response = client.post(
        f"{settings.API_V1_STR}/private/auth/session",
        json={
            "steamid64": steamid64,
            "is_superuser": is_superuser,
            "is_active": True,
            "name": "Test User",
        },
    )
    payload = response.json()
    return {"Authorization": f"Bearer {payload['access_token']}"}


def get_superuser_token_headers(client: TestClient) -> dict[str, str]:
    return _token_headers_from_private_session(
        client,
        steamid64=settings.SUPER_USER_STEAMID64,
        is_superuser=True,
    )


def get_user_token_headers(
    client: TestClient, steamid64: int | None = None
) -> dict[str, str]:
    return _token_headers_from_private_session(
        client,
        steamid64=steamid64 or random_steamid64(),
        is_superuser=False,
    )
