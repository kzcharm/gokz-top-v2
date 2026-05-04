from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import (
    User,
    UserCreate,
    UserPublic,
    UserRole,
    UserUpdate,
    normalize_user_roles,
)

from .player import (
    create_or_update_player_from_steam,
    get_player_by_steamid64,
    to_player_ref_public,
)


async def create_user(*, session: AsyncSession, user_create: UserCreate) -> User:
    steamid64 = int(user_create.steamid64)
    if not await get_player_by_steamid64(session=session, steamid64=steamid64):
        await create_or_update_player_from_steam(session=session, steamid64=steamid64)

    db_obj = User.model_validate(user_create)
    db_obj.roles = normalize_user_roles(user_create.roles)
    session.add(db_obj)
    await session.commit()
    await session.refresh(db_obj)
    return db_obj


async def update_user(
    *, session: AsyncSession, db_user: User, user_in: UserUpdate
) -> Any:
    user_data = user_in.model_dump(exclude_unset=True)
    if "roles" in user_data:
        user_data["roles"] = normalize_user_roles(user_data["roles"])
    db_user.sqlmodel_update(user_data)
    session.add(db_user)
    await session.commit()
    await session.refresh(db_user)
    return db_user


async def get_user_by_steamid64(
    *, session: AsyncSession, steamid64: int
) -> User | None:
    statement = select(User).where(User.steamid64 == steamid64)
    return (await session.exec(statement)).first()


async def get_or_create_user_from_steam(
    *, session: AsyncSession, steamid64: int | str
) -> User:
    steamid64_int = int(steamid64)
    await create_or_update_player_from_steam(session=session, steamid64=steamid64_int)

    db_user = await get_user_by_steamid64(session=session, steamid64=steamid64_int)
    is_bootstrap_superuser = steamid64_int == settings.SUPER_USER_STEAMID64

    if not db_user:
        roles = (
            [UserRole.SUPERUSER] if is_bootstrap_superuser else []
        )
        db_user = User(
            steamid64=steamid64_int,
            is_active=True,
            roles=roles,
        )
        session.add(db_user)
        try:
            await session.commit()
            await session.refresh(db_user)
            return db_user
        except IntegrityError:
            # Another request inserted this user concurrently.
            await session.rollback()
            existing_user = await get_user_by_steamid64(
                session=session, steamid64=steamid64_int
            )
            if not existing_user:
                raise
            db_user = existing_user

    normalized_roles = normalize_user_roles(db_user.roles)
    if is_bootstrap_superuser and UserRole.SUPERUSER not in normalized_roles:
        normalized_roles.append(UserRole.SUPERUSER)
        normalized_roles = normalize_user_roles(normalized_roles)

    if db_user.roles != normalized_roles:
        db_user.roles = normalized_roles
        session.add(db_user)
        await session.commit()
        await session.refresh(db_user)

    return db_user


async def to_user_public(*, session: AsyncSession, user: User) -> UserPublic:
    player = await get_player_by_steamid64(session=session, steamid64=user.steamid64)
    player_public = None
    if player:
        player_public = to_player_ref_public(player=player)
    return UserPublic(
        steamid64=str(user.steamid64),
        is_active=user.is_active,
        roles=normalize_user_roles(user.roles),
        created_at=user.created_at,
        last_visited_at=user.last_visited_at,
        player=player_public,
    )
