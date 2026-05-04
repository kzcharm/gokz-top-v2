from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.models import User
from tests.utils.utils import get_user_token_headers, random_steamid64


async def user_authentication_headers(
    *, client: AsyncClient, steamid64: int
) -> dict[str, str]:
    response = await client.post(
        f"{settings.API_V1_STR}/private/auth/session",
        json={
            "steamid64": steamid64,
            "roles": [],
            "is_active": True,
            "name": "Test User",
        },
    )
    payload = response.json()
    return {"Authorization": f"Bearer {payload['access_token']}"}


async def create_random_user(db: AsyncSession) -> User:
    steamid64 = random_steamid64()
    return await crud.get_or_create_user_from_steam(session=db, steamid64=steamid64)


async def authentication_token_from_steamid(
    *, client: AsyncClient, steamid64: int, db: AsyncSession
) -> dict[str, str]:
    await crud.get_or_create_user_from_steam(session=db, steamid64=steamid64)
    return await get_user_token_headers(client=client, steamid64=steamid64)
