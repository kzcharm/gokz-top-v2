from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import (
    PlayerSocialLink,
    PlayerSocialPlatform,
    PlayerVideoPlatformFollowerCache,
    VideoPlatformFollowerPublic,
    get_datetime_utc,
)
from app.services.player_social_links import build_player_social_link_url

logger = logging.getLogger(__name__)

VIDEO_FOLLOWER_PLATFORMS: tuple[PlayerSocialPlatform, ...] = (
    PlayerSocialPlatform.BILIBILI,
    PlayerSocialPlatform.YOUTUBE,
    PlayerSocialPlatform.TWITCH,
)
VIDEO_FOLLOWER_PLATFORM_PRIORITY = {
    platform: index for index, platform in enumerate(VIDEO_FOLLOWER_PLATFORMS)
}
_BILIBILI_BROWSER_HEADERS = {
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
}


def _parse_non_negative_int(value: object | None) -> int:
    if isinstance(value, bool):
        raise ValueError("Follower count was not numeric")
    if isinstance(value, int):
        if value >= 0:
            return value
    if isinstance(value, str):
        normalized = value.strip()
        if normalized.isdecimal():
            return int(normalized)
    raise ValueError("Follower count was not a non-negative integer")


def _truncate_error_message(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message[:500]


def _cache_reference_time(
    cache_row: PlayerVideoPlatformFollowerCache,
) -> datetime:
    return cache_row.fetched_at or cache_row.last_attempted_at


def _is_cache_fresh(
    cache_row: PlayerVideoPlatformFollowerCache,
    *,
    now: datetime,
) -> bool:
    ttl = timedelta(seconds=settings.VIDEO_PLATFORM_FOLLOWER_CACHE_TTL_SECONDS)
    return _cache_reference_time(cache_row) >= now - ttl


def _youtube_channel_params(account_identifier: str) -> dict[str, str]:
    if account_identifier.startswith("channel/"):
        return {"id": account_identifier.removeprefix("channel/")}
    if account_identifier.startswith("@"):
        return {"forHandle": account_identifier}
    if account_identifier.startswith("user/"):
        return {"forUsername": account_identifier.removeprefix("user/")}
    raise ValueError("YouTube follower refresh supports handles and channel IDs only")


async def fetch_bilibili_follower_count(*, account_identifier: str) -> int:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://api.bilibili.com/x/relation/stat",
            params={"vmid": account_identifier},
            headers=_BILIBILI_BROWSER_HEADERS,
        )
        response.raise_for_status()
        payload = response.json()

    if payload.get("code") != 0:
        raise ValueError(payload.get("message") or "Bilibili follower API error")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("Bilibili follower API returned an invalid payload")
    return _parse_non_negative_int(data.get("follower"))


async def fetch_youtube_follower_count(*, account_identifier: str) -> int:
    if not settings.YOUTUBE_API_KEY:
        raise RuntimeError("YouTube follower refresh credentials are not configured")

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://www.googleapis.com/youtube/v3/channels",
            params={
                "part": "statistics",
                "key": settings.YOUTUBE_API_KEY,
                **_youtube_channel_params(account_identifier),
            },
        )
        response.raise_for_status()
        payload = response.json()

    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("YouTube channel was not found")
    first_item = items[0]
    if not isinstance(first_item, dict):
        raise ValueError("YouTube channel API returned an invalid item")
    statistics = first_item.get("statistics")
    if not isinstance(statistics, dict):
        raise ValueError("YouTube channel API returned invalid statistics")
    if statistics.get("hiddenSubscriberCount") is True:
        raise ValueError("YouTube subscriber count is hidden")
    return _parse_non_negative_int(statistics.get("subscriberCount"))


async def _fetch_twitch_user_id(
    *,
    account_identifier: str,
    access_token: str,
) -> str:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://api.twitch.tv/helix/users",
            params={"login": account_identifier},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Client-Id": settings.TWITCH_CLIENT_ID or "",
            },
        )
        response.raise_for_status()
        payload = response.json()

    data = payload.get("data")
    if not isinstance(data, list) or not data:
        raise ValueError("Twitch user was not found")
    first_item = data[0]
    if not isinstance(first_item, dict) or not isinstance(first_item.get("id"), str):
        raise ValueError("Twitch user API returned an invalid payload")
    return first_item["id"]


async def fetch_twitch_follower_count(*, account_identifier: str) -> int:
    if not settings.TWITCH_CLIENT_ID or not settings.TWITCH_CLIENT_SECRET:
        raise RuntimeError("Twitch follower refresh credentials are not configured")

    from app.services.live_streams import _get_twitch_app_access_token

    access_token = await _get_twitch_app_access_token()
    broadcaster_id = await _fetch_twitch_user_id(
        account_identifier=account_identifier,
        access_token=access_token,
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://api.twitch.tv/helix/channels/followers",
            params={"broadcaster_id": broadcaster_id, "first": 1},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Client-Id": settings.TWITCH_CLIENT_ID or "",
            },
        )
        response.raise_for_status()
        payload = response.json()

    return _parse_non_negative_int(payload.get("total"))


async def fetch_video_platform_follower_count(*, link: PlayerSocialLink) -> int:
    if link.platform == PlayerSocialPlatform.BILIBILI:
        return await fetch_bilibili_follower_count(
            account_identifier=link.account_identifier
        )
    if link.platform == PlayerSocialPlatform.YOUTUBE:
        return await fetch_youtube_follower_count(
            account_identifier=link.account_identifier
        )
    if link.platform == PlayerSocialPlatform.TWITCH:
        return await fetch_twitch_follower_count(
            account_identifier=link.account_identifier
        )
    raise ValueError(f"Unsupported video follower platform: {link.platform}")


async def list_verified_video_platform_links_for_players(
    *,
    session: AsyncSession,
    steamid64s: Sequence[int],
) -> list[PlayerSocialLink]:
    if not steamid64s:
        return []

    statement = (
        select(PlayerSocialLink)
        .where(
            col(PlayerSocialLink.player_steamid64).in_(list(dict.fromkeys(steamid64s))),
            col(PlayerSocialLink.verified).is_(True),
            col(PlayerSocialLink.platform).in_(VIDEO_FOLLOWER_PLATFORMS),
        )
        .order_by(col(PlayerSocialLink.player_steamid64).asc())
    )
    return list((await session.exec(statement)).all())


async def _load_cache_rows_by_link_id(
    *,
    session: AsyncSession,
    link_ids: Sequence[Any],
) -> dict[Any, PlayerVideoPlatformFollowerCache]:
    if not link_ids:
        return {}

    statement = select(PlayerVideoPlatformFollowerCache).where(
        col(PlayerVideoPlatformFollowerCache.social_link_id).in_(list(link_ids))
    )
    return {row.social_link_id: row for row in (await session.exec(statement)).all()}


async def _upsert_follower_cache(
    *,
    session: AsyncSession,
    link: PlayerSocialLink,
    follower_count: int | None,
    fetched_at: datetime | None,
    attempted_at: datetime,
    error_message: str | None,
) -> None:
    cache_table = PlayerVideoPlatformFollowerCache.__table__  # type: ignore[attr-defined]
    insert_statement = pg_insert(cache_table).values(
        {
            "social_link_id": link.id,
            "player_steamid64": link.player_steamid64,
            "platform": link.platform,
            "account_identifier": link.account_identifier,
            "follower_count": follower_count,
            "fetched_at": fetched_at,
            "last_attempted_at": attempted_at,
            "error_message": error_message,
        }
    )
    upsert_statement = insert_statement.on_conflict_do_update(
        index_elements=[cache_table.c.social_link_id],
        set_={
            "player_steamid64": insert_statement.excluded.player_steamid64,
            "platform": insert_statement.excluded.platform,
            "account_identifier": insert_statement.excluded.account_identifier,
            "follower_count": insert_statement.excluded.follower_count,
            "fetched_at": insert_statement.excluded.fetched_at,
            "last_attempted_at": insert_statement.excluded.last_attempted_at,
            "error_message": insert_statement.excluded.error_message,
        },
    )
    await session.exec(upsert_statement)


async def refresh_stale_video_platform_follower_caches(
    *,
    session: AsyncSession,
    links: Sequence[PlayerSocialLink],
    now: datetime | None = None,
) -> None:
    current_now = now or get_datetime_utc()
    cache_rows = await _load_cache_rows_by_link_id(
        session=session,
        link_ids=[link.id for link in links],
    )
    stale_links = [
        link
        for link in links
        if link.id not in cache_rows
        or not _is_cache_fresh(cache_rows[link.id], now=current_now)
    ][: settings.VIDEO_PLATFORM_FOLLOWER_REFRESH_LIMIT]

    for link in stale_links:
        previous = cache_rows.get(link.id)
        try:
            follower_count = await fetch_video_platform_follower_count(link=link)
        except Exception as exc:
            logger.info(
                "Failed to refresh video platform followers",
                extra={
                    "social_link_id": str(link.id),
                    "platform": link.platform,
                    "player_steamid64": link.player_steamid64,
                },
                exc_info=True,
            )
            await _upsert_follower_cache(
                session=session,
                link=link,
                follower_count=previous.follower_count if previous is not None else None,
                fetched_at=previous.fetched_at if previous is not None else None,
                attempted_at=current_now,
                error_message=_truncate_error_message(exc),
            )
            continue

        await _upsert_follower_cache(
            session=session,
            link=link,
            follower_count=follower_count,
            fetched_at=current_now,
            attempted_at=current_now,
            error_message=None,
        )

    if stale_links:
        await session.commit()


def to_video_platform_follower_public(
    *,
    link: PlayerSocialLink,
    cache: PlayerVideoPlatformFollowerCache,
) -> VideoPlatformFollowerPublic | None:
    if cache.follower_count is None or cache.fetched_at is None:
        return None
    return VideoPlatformFollowerPublic(
        platform=link.platform,
        followers_count=cache.follower_count,
        url=build_player_social_link_url(
            platform=link.platform,
            account_identifier=link.account_identifier,
        ),
        updated_at=cache.fetched_at,
    )


def _best_follower_sort_key(
    public: VideoPlatformFollowerPublic,
) -> tuple[int, int]:
    return (
        public.followers_count,
        -VIDEO_FOLLOWER_PLATFORM_PRIORITY[public.platform],
    )


async def load_best_video_platform_followers_for_players(
    *,
    session: AsyncSession,
    steamid64s: Sequence[int],
) -> dict[int, VideoPlatformFollowerPublic]:
    links = await list_verified_video_platform_links_for_players(
        session=session,
        steamid64s=steamid64s,
    )
    await refresh_stale_video_platform_follower_caches(session=session, links=links)
    cache_rows = await _load_cache_rows_by_link_id(
        session=session,
        link_ids=[link.id for link in links],
    )

    best_by_player: dict[int, VideoPlatformFollowerPublic] = {}
    for link in links:
        cache_row = cache_rows.get(link.id)
        if cache_row is None:
            continue
        public = to_video_platform_follower_public(link=link, cache=cache_row)
        if public is None:
            continue
        current = best_by_player.get(link.player_steamid64)
        if current is None or _best_follower_sort_key(public) > _best_follower_sort_key(
            current
        ):
            best_by_player[link.player_steamid64] = public
    return best_by_player
