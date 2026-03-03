from typing import Any

from sqlmodel import Session, select

from app.core.config import settings
from app.models import PlayerPublic, User, UserCreate, UserPublic, UserUpdate

from .player import create_or_update_player_from_steam, get_player_by_steamid64


def create_user(*, session: Session, user_create: UserCreate) -> User:
    steamid64 = int(user_create.steamid64)
    if not get_player_by_steamid64(session=session, steamid64=steamid64):
        create_or_update_player_from_steam(session=session, steamid64=steamid64)

    db_obj = User.model_validate(user_create)
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    return db_obj


def update_user(*, session: Session, db_user: User, user_in: UserUpdate) -> Any:
    user_data = user_in.model_dump(exclude_unset=True)
    db_user.sqlmodel_update(user_data)
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user


def get_user_by_steamid64(*, session: Session, steamid64: int) -> User | None:
    statement = select(User).where(User.steamid64 == steamid64)
    return session.exec(statement).first()


def get_or_create_user_from_steam(*, session: Session, steamid64: int | str) -> User:
    steamid64_int = int(steamid64)
    create_or_update_player_from_steam(session=session, steamid64=steamid64_int)

    db_user = get_user_by_steamid64(session=session, steamid64=steamid64_int)
    should_be_superuser = steamid64_int == settings.SUPER_USER_STEAMID64

    if not db_user:
        db_user = User(
            steamid64=steamid64_int,
            is_superuser=should_be_superuser,
            is_active=True,
        )
        session.add(db_user)
        session.commit()
        session.refresh(db_user)
        return db_user

    if db_user.is_superuser != should_be_superuser:
        db_user.is_superuser = should_be_superuser
        session.add(db_user)
        session.commit()
        session.refresh(db_user)

    return db_user


def to_user_public(*, session: Session, user: User) -> UserPublic:
    player = get_player_by_steamid64(session=session, steamid64=user.steamid64)
    player_public = None
    if player:
        player_public = PlayerPublic(
            steamid64=str(player.steamid64),
            name=player.name,
            alias=player.alias,
            custom_id=player.custom_id,
            avatar_hash=player.avatar_hash,
            country=player.country,
            created_at=player.created_at,
            last_played_at=player.last_played_at,
            updated_at=player.updated_at,
        )
    return UserPublic(
        steamid64=str(user.steamid64),
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        created_at=user.created_at,
        last_visited_at=user.last_visited_at,
        player=player_public,
    )
