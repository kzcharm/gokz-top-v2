import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx
from sqlalchemy import case, false, func, literal, or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.crud.player_profile_field_change import (
    build_player_profile_field_status,
    get_player_profile_field_changes,
    player_profile_field_change_exists,
    upsert_player_profile_field_change,
)
from app.crud.player_profile_view import count_player_profile_views
from app.models import (
    LeaderboardPlayer,
    ModeScope,
    Player,
    PlayerProfileField,
    PlayerProfileFieldStatus,
    PlayerPublic,
    PlayerRefPublic,
    PlayerSettingsPublic,
    PlayerSettingsUpdate,
    PlayerUpdate,
    User,
)
from app.models.player import validate_player_custom_id

STEAM_COMMUNITY_HOSTS = {"steamcommunity.com", "www.steamcommunity.com"}
STEAM_ID_TYPE_INDIVIDUAL = 1
STEAM_ID_INSTANCE_DESKTOP = 1
PLAYER_SEARCH_WORD_SIMILARITY_OPERATOR = "<%"


class PlayerSettingsConflictError(ValueError):
    pass


@dataclass(slots=True)
class PlayerSearchInput:
    search_text: str
    search_text_lower: str
    exact_steamid64: int | None = None


def _build_individual_steamid64(*, account_id: int, universe: int) -> int | None:
    if account_id <= 0 or universe <= 0:
        return None

    return (
        (universe << 56)
        | (STEAM_ID_TYPE_INDIVIDUAL << 52)
        | (STEAM_ID_INSTANCE_DESKTOP << 32)
        | account_id
    )


def normalize_custom_id(custom_id: str | None) -> str | None:
    try:
        return validate_player_custom_id(custom_id)
    except ValueError:
        return None


def _extract_custom_id(profile_url: str | None) -> str | None:
    if not profile_url:
        return None
    match = re.search(r"/id/([^/]+)", profile_url)
    if not match:
        return None
    return normalize_custom_id(match.group(1))


def _extract_avatar_hash_from_url(avatar_url: str | None) -> str | None:
    if not avatar_url:
        return None
    match = re.search(r"/([a-f0-9]{40})(?:_(?:full|medium|small))?\\.jpg", avatar_url)
    if not match:
        return None
    return match.group(1)


def _steam_api_fallback_payload(steamid64: int) -> dict[str, str | bool | None]:
    return {
        "name": str(steamid64),
        "custom_id": None,
        "avatar_hash": None,
        "country": None,
        "fetched": False,
    }


def _parse_steam_profile_url(identifier: str) -> tuple[str, str] | None:
    parsed = urlsplit(identifier)
    host = parsed.netloc.split(":", maxsplit=1)[0].lower()
    if parsed.scheme not in {"http", "https"} or host not in STEAM_COMMUNITY_HOSTS:
        return None

    path_segments = [segment for segment in parsed.path.split("/") if segment]
    if len(path_segments) < 2:
        return None

    profile_type = path_segments[0].lower()
    profile_value = path_segments[1]
    if profile_type == "profiles" and profile_value.isdigit():
        return ("steamid64", profile_value)
    if profile_type == "id" and profile_value:
        return ("vanity", profile_value)
    return None


def _parse_direct_steam_identifier_to_steamid64(identifier: str) -> int | None:
    if identifier.isdigit():
        numeric_value = int(identifier)
        if 0 < numeric_value < 2**32:
            return _build_individual_steamid64(
                account_id=numeric_value,
                universe=1,
            )
        return numeric_value

    steam2_match = re.fullmatch(r"STEAM_(\d+):([01]):(\d+)", identifier)
    if steam2_match:
        universe = int(steam2_match.group(1))
        if universe == 0:
            universe = 1
        account_id = (int(steam2_match.group(3)) << 1) | int(
            steam2_match.group(2)
        )
        return _build_individual_steamid64(
            account_id=account_id,
            universe=universe,
        )

    steam3_match = re.fullmatch(r"\[U:(\d+):(\d+)(?::(\d+))?\]", identifier)
    if steam3_match:
        universe = int(steam3_match.group(1))
        account_id = int(steam3_match.group(2))
        return _build_individual_steamid64(
            account_id=account_id,
            universe=universe,
        )

    return None


async def _resolve_steam_vanity_url_to_steamid64(vanity_url: str) -> int | None:
    if not settings.STEAM_API_KEY:
        return None

    params = {
        "key": settings.STEAM_API_KEY,
        "vanityurl": vanity_url,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001/",
                params=params,
            )
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return None

    response_payload = payload.get("response")
    if not isinstance(response_payload, dict):
        return None

    try:
        if int(response_payload.get("success")) != 1:
            return None
        return int(response_payload["steamid"])
    except (KeyError, TypeError, ValueError):
        return None


def _normalize_steam_player_payload(
    *, steamid64: int, player: object
) -> dict[str, str | bool | None] | None:
    if not isinstance(player, dict):
        return None

    profile_url = player.get("profileurl")
    avatar_hash = player.get("avatarhash")
    if not avatar_hash:
        avatar_hash = _extract_avatar_hash_from_url(player.get("avatarfull"))

    return {
        "name": str(player.get("personaname") or steamid64),
        "custom_id": normalize_custom_id(_extract_custom_id(profile_url)),
        "avatar_hash": str(avatar_hash) if avatar_hash else None,
        "country": str(player.get("loccountrycode"))
        if player.get("loccountrycode")
        else None,
        "fetched": True,
    }


async def _fetch_players_from_steam_api(
    steamid64s: Sequence[int],
) -> dict[int, dict[str, str | bool | None]]:
    steam_data_by_steamid64 = await _fetch_players_from_steam_api_if_available(
        steamid64s,
    )
    return steam_data_by_steamid64 or {}


async def _fetch_players_from_steam_api_if_available(
    steamid64s: Sequence[int],
) -> dict[int, dict[str, str | bool | None]] | None:
    unique_steamid64s = list(dict.fromkeys(steamid64s))
    if not unique_steamid64s or not settings.STEAM_API_KEY:
        return None

    params = {
        "key": settings.STEAM_API_KEY,
        "steamids": ",".join(str(steamid64) for steamid64 in unique_steamid64s),
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
        return None

    players = payload.get("response", {}).get("players", [])
    if not isinstance(players, list):
        return None

    steam_data_by_steamid64: dict[int, dict[str, str | bool | None]] = {}
    for raw_player in players:
        if not isinstance(raw_player, dict):
            continue
        raw_steamid64 = raw_player.get("steamid")
        try:
            steamid64 = int(raw_steamid64)
        except (TypeError, ValueError):
            continue
        normalized = _normalize_steam_player_payload(
            steamid64=steamid64,
            player=raw_player,
        )
        if normalized is not None:
            steam_data_by_steamid64[steamid64] = normalized

    return steam_data_by_steamid64


async def _fetch_player_from_steam_api(
    steamid64: int,
) -> dict[str, str | bool | None]:
    steam_data_by_steamid64 = await _fetch_players_from_steam_api([steamid64])
    return steam_data_by_steamid64.get(steamid64, _steam_api_fallback_payload(steamid64))


async def get_player_by_steamid64(
    *, session: AsyncSession, steamid64: int
) -> Player | None:
    statement = select(Player).where(Player.steamid64 == steamid64)
    return (await session.exec(statement)).first()


async def _get_player_by_custom_id(
    *, session: AsyncSession, custom_id: str
) -> Player | None:
    statement = select(Player).where(Player.custom_id == custom_id)
    return (await session.exec(statement)).first()


async def _get_assignable_custom_id(
    *,
    session: AsyncSession,
    player_steamid64: int,
    custom_id: str | None,
) -> str | None:
    normalized_custom_id = normalize_custom_id(custom_id)
    if normalized_custom_id is None:
        return None

    existing_player = await _get_player_by_custom_id(
        session=session,
        custom_id=normalized_custom_id,
    )
    if existing_player is None or existing_player.steamid64 == player_steamid64:
        return normalized_custom_id
    return None


async def _player_country_is_locked(
    *, session: AsyncSession, player_steamid64: int
) -> bool:
    return await player_profile_field_change_exists(
        session=session,
        player_steamid64=player_steamid64,
        field=PlayerProfileField.COUNTRY,
    )


def _apply_steam_player_update(
    *,
    player: Player,
    steam_data: dict[str, str | bool | None],
    now: datetime,
    custom_id: str | None,
    country_locked: bool,
) -> None:
    player.name = steam_data["name"] or player.name
    if custom_id is not None and player.custom_id is None:
        player.custom_id = custom_id
    player.avatar_hash = steam_data["avatar_hash"] or player.avatar_hash
    if not country_locked:
        player.country = steam_data["country"] or player.country
    player.updated_at = now


async def _commit_player_update_with_custom_id_fallback(
    *,
    session: AsyncSession,
    steamid64: int,
    steam_data: dict[str, str | bool | None],
    now: datetime,
    custom_id: str | None,
) -> Player:
    player = await get_player_by_steamid64(session=session, steamid64=steamid64)
    if player is None:
        raise RuntimeError("Player missing during Steam update retry")

    country_locked = await _player_country_is_locked(
        session=session,
        player_steamid64=steamid64,
    )
    _apply_steam_player_update(
        player=player,
        steam_data=steam_data,
        now=now,
        custom_id=custom_id,
        country_locked=country_locked,
    )
    session.add(player)
    await session.commit()
    await session.refresh(player)
    return player


async def _build_player_search_input(
    *,
    session: AsyncSession,
    query: str,
) -> PlayerSearchInput:
    search_text = query.strip()
    exact_steamid64: int | None = None

    steam_profile = _parse_steam_profile_url(search_text)
    if steam_profile is not None:
        profile_type, profile_value = steam_profile
        if profile_type == "steamid64":
            exact_steamid64 = int(profile_value)
            search_text = profile_value
        else:
            exact_steamid64 = await _resolve_steam_vanity_url_to_steamid64(profile_value)
            search_text = profile_value
    else:
        direct_steamid64 = _parse_direct_steam_identifier_to_steamid64(search_text)
        if direct_steamid64 is not None:
            exact_steamid64 = direct_steamid64

    normalized_custom_id = normalize_custom_id(search_text)
    if normalized_custom_id is not None:
        search_text = normalized_custom_id
        custom_id_player = await _get_player_by_custom_id(
            session=session,
            custom_id=normalized_custom_id,
        )
        if custom_id_player is not None:
            exact_steamid64 = custom_id_player.steamid64

    return PlayerSearchInput(
        search_text=search_text,
        search_text_lower=search_text.lower(),
        exact_steamid64=exact_steamid64,
    )


async def get_player_by_identifier(
    *, session: AsyncSession, identifier: str
) -> Player | None:
    steam_profile = _parse_steam_profile_url(identifier)
    if steam_profile is not None:
        profile_type, profile_value = steam_profile
        if profile_type == "steamid64":
            return await get_player_by_steamid64(
                session=session,
                steamid64=int(profile_value),
            )

        steamid64 = await _resolve_steam_vanity_url_to_steamid64(profile_value)
        if steamid64 is None:
            return None
        return await get_player_by_steamid64(session=session, steamid64=steamid64)

    direct_steamid64 = _parse_direct_steam_identifier_to_steamid64(identifier)
    if direct_steamid64 is not None:
        return await get_player_by_steamid64(
            session=session,
            steamid64=direct_steamid64,
        )

    normalized_custom_id = normalize_custom_id(identifier)
    if normalized_custom_id is None:
        return None

    return await _get_player_by_custom_id(
        session=session,
        custom_id=normalized_custom_id,
    )


async def resolve_player_identifier_to_steamid64(
    *, session: AsyncSession, identifier: str
) -> int | None:
    steam_profile = _parse_steam_profile_url(identifier)
    if steam_profile is not None:
        profile_type, profile_value = steam_profile
        if profile_type == "steamid64":
            return int(profile_value)

        return await _resolve_steam_vanity_url_to_steamid64(profile_value)

    direct_steamid64 = _parse_direct_steam_identifier_to_steamid64(identifier)
    if direct_steamid64 is not None:
        return direct_steamid64

    normalized_custom_id = normalize_custom_id(identifier)
    if normalized_custom_id is None:
        return None

    player = await _get_player_by_custom_id(
        session=session,
        custom_id=normalized_custom_id,
    )
    if player is None:
        return None
    return player.steamid64


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


async def search_players(
    *,
    session: AsyncSession,
    q: str,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[Player], int]:
    search_input = await _build_player_search_input(session=session, query=q)
    search_term = search_input.search_text
    search_term_lower = search_input.search_text_lower
    prefix_pattern = f"{search_term_lower}%"
    ovr_scope = ModeScope.OVR

    lower_name = func.lower(col(Player.name))
    lower_alias = func.lower(func.coalesce(col(Player.alias), ""))
    lower_custom_id = func.lower(func.coalesce(col(Player.custom_id), ""))
    search_literal = literal(search_term_lower)
    tsquery = func.websearch_to_tsquery("simple", search_term)
    has_tsquery = func.numnode(tsquery) > 0

    exact_identifier_match = (
        col(Player.steamid64) == search_input.exact_steamid64
        if search_input.exact_steamid64 is not None
        else false()
    )
    prefix_match = or_(
        lower_custom_id.like(prefix_pattern),
        lower_alias.like(prefix_pattern),
        lower_name.like(prefix_pattern),
    )
    trigram_match = or_(
        search_literal.op(PLAYER_SEARCH_WORD_SIMILARITY_OPERATOR)(lower_custom_id),
        search_literal.op(PLAYER_SEARCH_WORD_SIMILARITY_OPERATOR)(lower_alias),
        search_literal.op(PLAYER_SEARCH_WORD_SIMILARITY_OPERATOR)(lower_name),
    )
    full_text_match = has_tsquery & col(Player.search_vector).bool_op("@@")(tsquery)

    rank_tier = case(
        (exact_identifier_match, 0),
        (lower_custom_id == search_term_lower, 1),
        (lower_alias == search_term_lower, 2),
        (lower_name == search_term_lower, 3),
        (lower_custom_id.like(prefix_pattern), 4),
        (lower_alias.like(prefix_pattern), 5),
        (lower_name.like(prefix_pattern), 6),
        else_=7,
    )
    full_text_rank = case(
        (has_tsquery, func.ts_rank_cd(col(Player.search_vector), tsquery, 32)),
        else_=0.0,
    )
    trigram_rank = func.greatest(
        func.word_similarity(search_term_lower, lower_custom_id),
        func.word_similarity(search_term_lower, lower_alias),
        func.word_similarity(search_term_lower, lower_name),
    )
    rating_rank = func.coalesce(col(LeaderboardPlayer.rating), 0)

    base_statement = (
        select(Player)
        .outerjoin(
            LeaderboardPlayer,
            (col(LeaderboardPlayer.steamid64) == col(Player.steamid64))
            & (col(LeaderboardPlayer.scope) == ovr_scope),
        )
        .where(
            or_(
                exact_identifier_match,
                prefix_match,
                full_text_match,
                trigram_match,
            )
        )
    )
    count_statement = select(func.count()).select_from(base_statement.subquery())
    count = (await session.exec(count_statement)).one()

    statement = (
        base_statement.order_by(
            rank_tier.asc(),
            full_text_rank.desc(),
            trigram_rank.desc(),
            rating_rank.desc(),
            col(Player.steamid64).desc(),
        )
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
    fetched_from_steam = steam_data.get("fetched") is True

    player = await get_player_by_steamid64(session=session, steamid64=steamid64)
    if player:
        if fetched_from_steam:
            custom_id = await _get_assignable_custom_id(
                session=session,
                player_steamid64=steamid64,
                custom_id=steam_data["custom_id"],
            )
            country_locked = await _player_country_is_locked(
                session=session,
                player_steamid64=steamid64,
            )
            _apply_steam_player_update(
                player=player,
                steam_data=steam_data,
                now=now,
                custom_id=custom_id,
                country_locked=country_locked,
            )
            session.add(player)
            try:
                await session.commit()
                await session.refresh(player)
            except IntegrityError:
                await session.rollback()
                player = await _commit_player_update_with_custom_id_fallback(
                    session=session,
                    steamid64=steamid64,
                    steam_data=steam_data,
                    now=now,
                    custom_id=None,
                )
        return player

    custom_id = await _get_assignable_custom_id(
        session=session,
        player_steamid64=steamid64,
        custom_id=steam_data["custom_id"],
    )
    player = Player(
        steamid64=steamid64,
        name=steam_data["name"] or str(steamid64),
        custom_id=custom_id,
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
        if existing_player is not None:
            if fetched_from_steam:
                custom_id = await _get_assignable_custom_id(
                    session=session,
                    player_steamid64=steamid64,
                    custom_id=steam_data["custom_id"],
                )
                return await _commit_player_update_with_custom_id_fallback(
                    session=session,
                    steamid64=steamid64,
                    steam_data=steam_data,
                    now=now,
                    custom_id=custom_id,
                )
            return existing_player

        player = Player(
            steamid64=steamid64,
            name=steam_data["name"] or str(steamid64),
            custom_id=None,
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
            await session.rollback()
            existing_player = await get_player_by_steamid64(
                session=session,
                steamid64=steamid64,
            )
            if existing_player is not None:
                return existing_player
            raise


async def create_or_update_player_from_steam_if_fetched(
    *, session: AsyncSession, steamid64: int
) -> tuple[Player | None, bool]:
    steam_data = await _fetch_player_from_steam_api(steamid64)
    return await create_or_update_player_from_steam_data_if_fetched(
        session=session,
        steamid64=steamid64,
        steam_data=steam_data,
    )


async def create_or_update_player_from_steam_data_if_fetched(
    *,
    session: AsyncSession,
    steamid64: int,
    steam_data: dict[str, str | bool | None] | None,
) -> tuple[Player | None, bool]:
    now = datetime.now(UTC)
    if not steam_data or steam_data.get("fetched") is not True:
        return None, False

    player = await get_player_by_steamid64(session=session, steamid64=steamid64)
    if player:
        custom_id = await _get_assignable_custom_id(
            session=session,
            player_steamid64=steamid64,
            custom_id=steam_data["custom_id"],
        )
        country_locked = await _player_country_is_locked(
            session=session,
            player_steamid64=steamid64,
        )
        _apply_steam_player_update(
            player=player,
            steam_data=steam_data,
            now=now,
            custom_id=custom_id,
            country_locked=country_locked,
        )
        session.add(player)
        try:
            await session.commit()
            await session.refresh(player)
        except IntegrityError:
            await session.rollback()
            player = await _commit_player_update_with_custom_id_fallback(
                session=session,
                steamid64=steamid64,
                steam_data=steam_data,
                now=now,
                custom_id=None,
            )
        return player, False

    custom_id = await _get_assignable_custom_id(
        session=session,
        player_steamid64=steamid64,
        custom_id=steam_data["custom_id"],
    )
    player = Player(
        steamid64=steamid64,
        name=steam_data["name"] or str(steamid64),
        custom_id=custom_id,
        avatar_hash=steam_data["avatar_hash"],
        country=steam_data["country"],
        created_at=now,
        updated_at=now,
    )
    session.add(player)
    try:
        await session.commit()
        await session.refresh(player)
        return player, True
    except IntegrityError:
        # Another request inserted this player concurrently.
        await session.rollback()
        existing_player = await get_player_by_steamid64(
            session=session, steamid64=steamid64
        )
        if existing_player is not None:
            custom_id = await _get_assignable_custom_id(
                session=session,
                player_steamid64=steamid64,
                custom_id=steam_data["custom_id"],
            )
            existing_player = await _commit_player_update_with_custom_id_fallback(
                session=session,
                steamid64=steamid64,
                steam_data=steam_data,
                now=now,
                custom_id=custom_id,
            )
            return existing_player, False

        player = Player(
            steamid64=steamid64,
            name=steam_data["name"] or str(steamid64),
            custom_id=None,
            avatar_hash=steam_data["avatar_hash"],
            country=steam_data["country"],
            created_at=now,
            updated_at=now,
        )
        session.add(player)
        try:
            await session.commit()
            await session.refresh(player)
            return player, True
        except IntegrityError:
            await session.rollback()
            existing_player = await get_player_by_steamid64(
                session=session,
                steamid64=steamid64,
            )
            if existing_player is not None:
                return existing_player, False
            raise


async def update_player(
    *, session: AsyncSession, db_player: Player, player_in: PlayerUpdate
) -> Player:
    now = datetime.now(UTC)
    player_data = player_in.model_dump(exclude_unset=True)
    db_player.sqlmodel_update(player_data)
    if "country" in player_data and player_data["country"] is not None:
        await upsert_player_profile_field_change(
            session=session,
            player_steamid64=db_player.steamid64,
            field=PlayerProfileField.COUNTRY,
            changed_at=now,
        )
    db_player.updated_at = now
    session.add(db_player)
    await session.commit()
    await session.refresh(db_player)
    return db_player


async def get_player_settings(
    *, session: AsyncSession, player: Player, now: datetime | None = None
) -> PlayerSettingsPublic:
    resolved_now = now or datetime.now(UTC)
    changes = await get_player_profile_field_changes(
        session=session,
        player_steamid64=player.steamid64,
    )
    alias_changed_at = changes.get(PlayerProfileField.ALIAS)
    custom_id_changed_at = changes.get(PlayerProfileField.CUSTOM_ID)
    country_changed_at = changes.get(PlayerProfileField.COUNTRY)
    country_locked = country_changed_at is not None
    return PlayerSettingsPublic(
        player=to_player_public(player=player),
        alias=build_player_profile_field_status(
            changed_at=alias_changed_at.changed_at if alias_changed_at else None,
            now=resolved_now,
        ),
        custom_id=build_player_profile_field_status(
            changed_at=custom_id_changed_at.changed_at if custom_id_changed_at else None,
            now=resolved_now,
        ),
        country=PlayerProfileFieldStatus(
            last_changed_at=country_changed_at.changed_at if country_changed_at else None,
            next_available_at=None,
            can_change=True,
        ),
        country_locked=country_locked,
    )


def _ensure_profile_text_value(*, field_name: str, value: str | None) -> str:
    if value is None:
        raise ValueError(f"{field_name} cannot be cleared")
    if not value.strip():
        raise ValueError(f"{field_name} cannot be blank")
    return value


def _ensure_can_change_field(
    *,
    field_name: str,
    status: PlayerProfileFieldStatus,
) -> None:
    if not status.can_change:
        raise PermissionError(f"{field_name} can only be changed once every 30 days")


async def update_player_settings(
    *,
    session: AsyncSession,
    player: Player,
    settings_in: PlayerSettingsUpdate,
) -> PlayerSettingsPublic:
    now = datetime.now(UTC)
    player_data = settings_in.model_dump(exclude_unset=True)
    current_settings = await get_player_settings(session=session, player=player, now=now)
    changed_fields: list[PlayerProfileField] = []

    if "alias" in player_data:
        alias = _ensure_profile_text_value(
            field_name=PlayerProfileField.ALIAS.value,
            value=settings_in.alias,
        )
        if alias != player.alias:
            _ensure_can_change_field(
                field_name=PlayerProfileField.ALIAS.value,
                status=current_settings.alias,
            )
            player.alias = alias
            changed_fields.append(PlayerProfileField.ALIAS)

    if "custom_id" in player_data:
        custom_id = _ensure_profile_text_value(
            field_name=PlayerProfileField.CUSTOM_ID.value,
            value=settings_in.custom_id,
        )
        if custom_id != player.custom_id:
            _ensure_can_change_field(
                field_name=PlayerProfileField.CUSTOM_ID.value,
                status=current_settings.custom_id,
            )
            existing_player = await _get_player_by_custom_id(
                session=session,
                custom_id=custom_id,
            )
            if (
                existing_player is not None
                and existing_player.steamid64 != player.steamid64
            ):
                raise PlayerSettingsConflictError("custom_id is already in use")
            player.custom_id = custom_id
            changed_fields.append(PlayerProfileField.CUSTOM_ID)

    if "country" in player_data:
        country = _ensure_profile_text_value(
            field_name=PlayerProfileField.COUNTRY.value,
            value=settings_in.country,
        )
        if country != player.country:
            player.country = country
            changed_fields.append(PlayerProfileField.COUNTRY)

    if changed_fields:
        player.updated_at = now
        session.add(player)
        for field in changed_fields:
            await upsert_player_profile_field_change(
                session=session,
                player_steamid64=player.steamid64,
                field=field,
                changed_at=now,
            )
        await session.commit()
        await session.refresh(player)

    return await get_player_settings(session=session, player=player, now=now)


async def load_website_user_steamid64s(
    *, session: AsyncSession, steamid64s: Sequence[int]
) -> set[int]:
    unique_steamid64s = tuple(dict.fromkeys(steamid64s))
    if not unique_steamid64s:
        return set()

    statement = select(User.steamid64).where(col(User.steamid64).in_(unique_steamid64s))
    return set((await session.exec(statement)).all())


async def to_player_publics(
    *, session: AsyncSession, players: Sequence[Player]
) -> list[PlayerPublic]:
    website_user_steamid64s = await load_website_user_steamid64s(
        session=session,
        steamid64s=[player.steamid64 for player in players],
    )
    return [
        to_player_public(
            player=player,
            is_website_user=player.steamid64 in website_user_steamid64s,
        )
        for player in players
    ]


def to_player_public(
    *, player: Player, profile_views: int = 0, is_website_user: bool = False
) -> PlayerPublic:
    return PlayerPublic(
        steamid64=str(player.steamid64),
        name=player.name,
        alias=player.alias,
        custom_id=normalize_custom_id(player.custom_id),
        avatar_hash=player.avatar_hash,
        country=player.country,
        created_at=player.created_at,
        last_played_at=player.last_played_at,
        updated_at=player.updated_at,
        is_website_user=is_website_user,
        profile_views=profile_views,
    )


def get_player_display_name(*, player: Player) -> str:
    return player.alias or player.name


def to_player_ref_public(*, player: Player) -> PlayerRefPublic:
    return PlayerRefPublic(
        steamid64=str(player.steamid64),
        display_name=get_player_display_name(player=player),
    )


async def to_player_public_with_profile_views(
    *,
    session: AsyncSession,
    player: Player,
) -> PlayerPublic:
    profile_views = await count_player_profile_views(
        session=session,
        target_steamid64=player.steamid64,
    )
    website_user_steamid64s = await load_website_user_steamid64s(
        session=session, steamid64s=[player.steamid64]
    )
    return to_player_public(
        player=player,
        profile_views=profile_views,
        is_website_user=player.steamid64 in website_user_steamid64s,
    )
