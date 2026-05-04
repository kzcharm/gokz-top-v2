import pytest
from fastapi.encoders import jsonable_encoder
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.models import Player, User, UserCreate, UserRole, UserUpdate
from tests.utils.utils import random_steamid64


@pytest.mark.asyncio
async def test_create_user(db: AsyncSession) -> None:
    steamid64 = random_steamid64()
    user_in = UserCreate(steamid64=steamid64)

    user = await crud.create_user(session=db, user_create=user_in)

    assert user.steamid64 == steamid64
    assert user.is_active is True
    assert user.roles == []


@pytest.mark.asyncio
async def test_create_user_creates_player(db: AsyncSession) -> None:
    steamid64 = random_steamid64()
    user_in = UserCreate(steamid64=steamid64)

    await crud.create_user(session=db, user_create=user_in)
    player = await crud.get_player_by_steamid64(session=db, steamid64=steamid64)

    assert player is not None
    assert player.steamid64 == steamid64
    assert player.name


@pytest.mark.asyncio
async def test_get_user_by_steamid64(db: AsyncSession) -> None:
    steamid64 = random_steamid64()
    created = await crud.get_or_create_user_from_steam(session=db, steamid64=steamid64)

    fetched = await crud.get_user_by_steamid64(session=db, steamid64=steamid64)

    assert fetched is not None
    assert fetched.steamid64 == created.steamid64
    assert fetched.steamid64 == steamid64


@pytest.mark.asyncio
async def test_get_or_create_user_from_steam_is_idempotent(db: AsyncSession) -> None:
    steamid64 = random_steamid64()

    first = await crud.get_or_create_user_from_steam(session=db, steamid64=steamid64)
    second = await crud.get_or_create_user_from_steam(session=db, steamid64=steamid64)

    assert first.steamid64 == second.steamid64
    assert first.steamid64 == second.steamid64


@pytest.mark.asyncio
async def test_get_or_create_user_from_steam_sets_superuser_for_configured_id(
    db: AsyncSession,
) -> None:
    user = await crud.get_or_create_user_from_steam(
        session=db,
        steamid64=settings.SUPER_USER_STEAMID64,
    )

    assert user.roles == [UserRole.SUPERUSER]


@pytest.mark.asyncio
async def test_get_or_create_user_from_steam_preserves_manual_roles_for_non_configured_id(
    db: AsyncSession,
) -> None:
    steamid64 = random_steamid64()
    user = await crud.get_or_create_user_from_steam(session=db, steamid64=steamid64)
    user.roles = [UserRole.SERVER_OWNER, UserRole.MAP_ADMIN]
    db.add(user)
    await db.commit()
    await db.refresh(user)

    refreshed = await crud.get_or_create_user_from_steam(
        session=db, steamid64=steamid64
    )

    assert refreshed.roles == [UserRole.MAP_ADMIN, UserRole.SERVER_OWNER]


@pytest.mark.asyncio
async def test_update_user(db: AsyncSession) -> None:
    steamid64 = random_steamid64()
    user = await crud.get_or_create_user_from_steam(session=db, steamid64=steamid64)

    update = UserUpdate(
        is_active=False,
        roles=[UserRole.SERVER_OWNER, UserRole.SUPERUSER],
    )
    updated = await crud.update_user(session=db, db_user=user, user_in=update)

    assert updated.is_active is False
    assert updated.roles == [UserRole.SUPERUSER, UserRole.SERVER_OWNER]


@pytest.mark.asyncio
async def test_to_user_public_includes_player(db: AsyncSession) -> None:
    steamid64 = random_steamid64()
    user = await crud.get_or_create_user_from_steam(session=db, steamid64=steamid64)

    user_public = await crud.to_user_public(session=db, user=user)

    assert user_public.steamid64 == str(steamid64)
    assert user_public.player is not None
    assert user_public.player.steamid64 == str(steamid64)

    same_user = await db.get(type(user), user.steamid64)
    assert same_user is not None
    assert (
        jsonable_encoder(user)["steamid64"] == jsonable_encoder(same_user)["steamid64"]
    )


@pytest.mark.asyncio
async def test_get_or_create_user_from_steam_handles_duplicate_insert_race(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steamid64 = random_steamid64()
    db.add(Player(steamid64=steamid64, name=f"player_{steamid64}"))
    db.add(User(steamid64=steamid64, is_active=True, roles=[]))
    await db.commit()

    async def _noop_create_or_update_player(
        *, session: AsyncSession, steamid64: int
    ) -> Player:
        player = await crud.get_player_by_steamid64(session=session, steamid64=steamid64)
        assert player is not None
        return player

    original_get_user = crud.get_user_by_steamid64
    calls = 0

    async def _stale_get_user(*, session: AsyncSession, steamid64: int) -> User | None:
        nonlocal calls
        calls += 1
        if calls == 1:
            return None
        return await original_get_user(session=session, steamid64=steamid64)

    monkeypatch.setattr(
        "app.crud.user.create_or_update_player_from_steam",
        _noop_create_or_update_player,
    )
    monkeypatch.setattr("app.crud.user.get_user_by_steamid64", _stale_get_user)

    user = await crud.get_or_create_user_from_steam(session=db, steamid64=steamid64)

    assert user.steamid64 == steamid64
    assert calls >= 2
