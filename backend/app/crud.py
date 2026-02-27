import re
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlmodel import Session, select

from app.core.config import settings
from app.models import (
    Item,
    ItemCreate,
    Player,
    PlayerPublic,
    User,
    UserCreate,
    UserPublic,
    UserUpdate,
)


def _extract_custom_id(profile_url: str | None) -> str | None:
    if not profile_url:
        return None
    match = re.search(r"/id/([^/]+)", profile_url)
    if not match:
        return None
    return match.group(1)


def _extract_avatar_hash_from_url(avatar_url: str | None) -> str | None:
    if not avatar_url:
        return None
    match = re.search(r"/([a-f0-9]{40})(?:_(?:full|medium|small))?\\.jpg", avatar_url)
    if not match:
        return None
    return match.group(1)


def _fetch_player_from_steam_api(steamid64: int) -> dict[str, str | None]:
    if not settings.STEAM_API_KEY:
        return {
            "name": str(steamid64),
            "custom_id": None,
            "avatar_hash": None,
            "country": None,
        }

    params = {
        "key": settings.STEAM_API_KEY,
        "steamids": str(steamid64),
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/",
                params=params,
            )
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return {
            "name": str(steamid64),
            "custom_id": None,
            "avatar_hash": None,
            "country": None,
        }

    players = payload.get("response", {}).get("players", [])
    if not players:
        return {
            "name": str(steamid64),
            "custom_id": None,
            "avatar_hash": None,
            "country": None,
        }

    player = players[0]
    profile_url = player.get("profileurl")
    avatar_hash = player.get("avatarhash")
    if not avatar_hash:
        avatar_hash = _extract_avatar_hash_from_url(player.get("avatarfull"))

    return {
        "name": str(player.get("personaname") or steamid64),
        "custom_id": _extract_custom_id(profile_url),
        "avatar_hash": str(avatar_hash) if avatar_hash else None,
        "country": str(player.get("loccountrycode"))
        if player.get("loccountrycode")
        else None,
    }


def get_player_by_steamid64(*, session: Session, steamid64: int) -> Player | None:
    statement = select(Player).where(Player.steamid64 == steamid64)
    return session.exec(statement).first()


def create_or_update_player_from_steam(*, session: Session, steamid64: int) -> Player:
    now = datetime.now(timezone.utc)
    steam_data = _fetch_player_from_steam_api(steamid64)

    player = get_player_by_steamid64(session=session, steamid64=steamid64)
    if player:
        player.name = steam_data["name"] or player.name
        player.custom_id = steam_data["custom_id"] or player.custom_id
        player.avatar_hash = steam_data["avatar_hash"] or player.avatar_hash
        player.country = steam_data["country"] or player.country
        player.updated_at = now
        session.add(player)
        session.commit()
        session.refresh(player)
        return player

    player = Player(
        steamid64=steamid64,
        name=steam_data["name"] or str(steamid64),
        custom_id=steam_data["custom_id"],
        avatar_hash=steam_data["avatar_hash"],
        country=steam_data["country"],
        created_at=now,
        updated_at=now,
    )
    session.add(player)
    session.commit()
    session.refresh(player)
    return player


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
    player_public = PlayerPublic.model_validate(player) if player else None
    return UserPublic(
        id=user.id,
        steamid64=user.steamid64,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        created_at=user.created_at,
        player=player_public,
    )


def create_item(*, session: Session, item_in: ItemCreate, owner_id: uuid.UUID) -> Item:
    db_item = Item.model_validate(item_in, update={"owner_id": owner_id})
    session.add(db_item)
    session.commit()
    session.refresh(db_item)
    return db_item
