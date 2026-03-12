import re
from datetime import UTC, datetime

import httpx
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import Player, PlayerPublic, PlayerUpdate


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


async def _fetch_player_from_steam_api(steamid64: int) -> dict[str, str | None]:
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
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
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


async def get_player_by_steamid64(
    *, session: AsyncSession, steamid64: int
) -> Player | None:
    statement = select(Player).where(Player.steamid64 == steamid64)
    return (await session.exec(statement)).first()


async def read_players(
    *,
    session: AsyncSession,
    offset: int = 0,
    limit: int = 20,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple[list[Player], int]:
    count_statement = select(func.count()).select_from(Player)
    count = (await session.exec(count_statement)).one()

    sort_column = col(Player.created_at)
    if sort_by == "last_played_at":
        sort_column = col(Player.last_played_at)

    sort_direction = sort_column.asc() if sort_order == "asc" else sort_column.desc()
    statement = (
        select(Player)
        .order_by(sort_direction.nullslast(), col(Player.steamid64).desc())
        .offset(offset)
        .limit(limit)
    )
    players = list((await session.exec(statement)).all())
    return players, count


async def read_players_batch(
    *, session: AsyncSession, steamid64s: list[int]
) -> list[Player | None]:
    if not steamid64s:
        return []

    statement = select(Player).where(col(Player.steamid64).in_(steamid64s))
    players = list((await session.exec(statement)).all())
    players_by_steamid64 = {player.steamid64: player for player in players}
    return [players_by_steamid64.get(steamid64) for steamid64 in steamid64s]


async def create_or_update_player_from_steam(
    *, session: AsyncSession, steamid64: int
) -> Player:
    now = datetime.now(UTC)
    steam_data = await _fetch_player_from_steam_api(steamid64)

    player = await get_player_by_steamid64(session=session, steamid64=steamid64)
    if player:
        player.name = steam_data["name"] or player.name
        player.custom_id = steam_data["custom_id"] or player.custom_id
        player.avatar_hash = steam_data["avatar_hash"] or player.avatar_hash
        player.country = steam_data["country"] or player.country
        player.updated_at = now
        session.add(player)
        await session.commit()
        await session.refresh(player)
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
    try:
        await session.commit()
        await session.refresh(player)
        return player
    except IntegrityError:
        # Another request inserted this player concurrently.
        await session.rollback()
        existing_player = await get_player_by_steamid64(
            session=session, steamid64=steamid64
        )
        if not existing_player:
            raise
        existing_player.name = steam_data["name"] or existing_player.name
        existing_player.custom_id = steam_data["custom_id"] or existing_player.custom_id
        existing_player.avatar_hash = (
            steam_data["avatar_hash"] or existing_player.avatar_hash
        )
        existing_player.country = steam_data["country"] or existing_player.country
        existing_player.updated_at = now
        session.add(existing_player)
        await session.commit()
        await session.refresh(existing_player)
        return existing_player


async def update_player(
    *, session: AsyncSession, db_player: Player, player_in: PlayerUpdate
) -> Player:
    player_data = player_in.model_dump(exclude_unset=True)
    db_player.sqlmodel_update(player_data)
    db_player.updated_at = datetime.now(UTC)
    session.add(db_player)
    await session.commit()
    await session.refresh(db_player)
    return db_player


def to_player_public(*, player: Player) -> PlayerPublic:
    return PlayerPublic(
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
