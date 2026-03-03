import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import User


@pytest.mark.asyncio
async def test_create_auth_session(client: AsyncClient, db: AsyncSession) -> None:
    steamid64 = 76561199099999999
    response = await client.post(
        f"{settings.API_V1_STR}/private/auth/session",
        json={
            "steamid64": steamid64,
            "is_superuser": False,
            "is_active": True,
            "name": "Pollo Listo",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert "access_token" in payload

    user = (await db.exec(select(User).where(User.steamid64 == steamid64))).first()
    assert user
