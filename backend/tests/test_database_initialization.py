"""Local bootstrap is idempotent and keeps local fixtures out of production."""

import pytest
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import db as database
from app.models import Player, PlayerWebhook, User, UserRole
from tests.utils.utils import random_steamid64


@pytest.mark.asyncio
async def test_async_database_initialization_creates_local_superuser_once(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steamid = random_steamid64()
    monkeypatch.setattr(database.settings, "SUPER_USER_STEAMID64", steamid)
    await database.init_db_async(db)
    await database.init_db_async(db)
    user = await db.get(User, steamid)
    assert user is not None and UserRole.SUPERUSER in user.roles
    assert await db.get(Player, steamid) is not None
    webhooks = (
        await db.exec(
            select(PlayerWebhook).where(col(PlayerWebhook.player_steamid64) == steamid)
        )
    ).all()
    assert len(webhooks) == 1
    await db.delete(webhooks[0])
    await db.flush()
    monkeypatch.setattr(database.settings, "ENVIRONMENT", "production")
    await database.init_db_async(db)
    assert not (
        await db.exec(
            select(PlayerWebhook).where(col(PlayerWebhook.player_steamid64) == steamid)
        )
    ).all()
