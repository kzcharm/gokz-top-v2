import re
from datetime import UTC, datetime

import httpx
from sqlmodel import Session, select

from app.core.config import settings
from app.models import Player


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
    now = datetime.now(UTC)
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
