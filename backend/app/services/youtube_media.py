from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import re
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

import httpx
import psycopg
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.core.db import async_session_maker
from app.models import (
    MediaPost,
    PlayerSocialLink,
    PlayerSocialPlatform,
    get_datetime_utc,
)
from app.services import r2_storage

logger = logging.getLogger(__name__)
MEDIA_SYNC_LOCK_ID = int.from_bytes(
    hashlib.sha256(b"gokz-top-v2:media-runner").digest()[:8],
    "big",
    signed=True,
)
MEDIA_RETENTION_DAYS = 90
YOUTUBE_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
YOUTUBE_PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
YOUTUBE_WEBSUB_HUB_URL = "https://pubsubhubbub.appspot.com/subscribe"
YOUTUBE_WEBSUB_TOPIC_URL = "https://www.youtube.com/xml/feeds/videos.xml"
YOUTUBE_WEBSUB_LEASE_SECONDS = 10 * 24 * 60 * 60
YOUTUBE_WEBSUB_RENEWAL_SECONDS = 7 * 24 * 60 * 60
YOUTUBE_WEBSUB_FAILURE_RETRY_SECONDS = 5 * 60


def _youtube_channel_params(account_identifier: str) -> dict[str, str]:
    if account_identifier.startswith("channel/"):
        return {"id": account_identifier.removeprefix("channel/")}
    if account_identifier.startswith("@"):
        return {"forHandle": account_identifier}
    raise ValueError("Unsupported YouTube channel identifier")


def youtube_websub_callback_url() -> str:
    return (
        f"{settings.BACKEND_PUBLIC_URL.rstrip('/')}"
        f"{settings.API_V1_STR}/webhooks/youtube"
    )


def youtube_websub_is_configured() -> bool:
    return bool(settings.YOUTUBE_WEBSUB_ENABLED and settings.YOUTUBE_WEBSUB_SECRET)


def is_youtube_websub_topic(topic: str) -> bool:
    parsed = urlparse(topic)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "www.youtube.com"
        or parsed.path != "/xml/feeds/videos.xml"
    ):
        return False
    try:
        channel_ids = parse_qs(parsed.query, strict_parsing=True).get("channel_id", [])
    except ValueError:
        return False
    return len(channel_ids) == 1 and bool(
        re.fullmatch(r"UC[A-Za-z0-9_-]{20,}", channel_ids[0])
    )


def verify_youtube_websub_signature(*, body: bytes, signature: str | None) -> bool:
    secret = settings.YOUTUBE_WEBSUB_SECRET
    if not youtube_websub_is_configured() or not secret or signature is None:
        return False
    algorithm, separator, received_digest = signature.partition("=")
    if separator != "=" or algorithm not in {"sha1", "sha256"} or not received_digest:
        return False
    expected_digest = hmac.new(
        secret.encode(), body, getattr(hashlib, algorithm)
    ).hexdigest()
    return hmac.compare_digest(received_digest, expected_digest)


def _parse_published(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (
        parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    )


def _parse_view_count(value: object) -> int:
    try:
        return max(0, int(str(value)))
    except (TypeError, ValueError):
        return 0


def _thumbnail_url(snippet: dict[str, Any]) -> str | None:
    thumbnails = snippet.get("thumbnails")
    if not isinstance(thumbnails, dict):
        return None
    for size in ("maxres", "standard", "high", "medium", "default"):
        thumbnail = thumbnails.get(size)
        if isinstance(thumbnail, dict):
            url = thumbnail.get("url")
            if isinstance(url, str):
                return url
    return None


async def fetch_youtube_posts(
    account_identifier: str, *, page_size: int = 30
) -> list[dict[str, Any]]:
    if not settings.YOUTUBE_API_KEY:
        raise RuntimeError("YouTube media sync credentials are not configured")

    async with httpx.AsyncClient(timeout=15.0) as client:
        channel_response = await client.get(
            YOUTUBE_CHANNELS_URL,
            params={
                "part": "id,contentDetails",
                "key": settings.YOUTUBE_API_KEY,
                **_youtube_channel_params(account_identifier),
            },
        )
        channel_response.raise_for_status()
        channel_payload = channel_response.json()

        channels = channel_payload.get("items")
        if not isinstance(channels, list) or not channels:
            raise ValueError("YouTube channel was not found")
        first_channel = channels[0]
        if not isinstance(first_channel, dict):
            raise ValueError("YouTube channel API returned an invalid payload")
        content_details = first_channel.get("contentDetails")
        related_playlists = (
            content_details.get("relatedPlaylists")
            if isinstance(content_details, dict)
            else None
        )
        uploads_playlist_id = (
            related_playlists.get("uploads")
            if isinstance(related_playlists, dict)
            else None
        )
        if not isinstance(uploads_playlist_id, str) or not uploads_playlist_id:
            raise ValueError("YouTube channel does not expose an uploads playlist")

        playlist_response = await client.get(
            YOUTUBE_PLAYLIST_ITEMS_URL,
            params={
                "part": "snippet,contentDetails",
                "key": settings.YOUTUBE_API_KEY,
                "playlistId": uploads_playlist_id,
                "maxResults": page_size,
            },
        )
        playlist_response.raise_for_status()
        playlist_payload = playlist_response.json()

    items = playlist_payload.get("items")
    playlist_items = (
        [item for item in items if isinstance(item, dict)]
        if isinstance(items, list)
        else []
    )
    video_ids: list[str] = []
    for item in playlist_items:
        snippet = item.get("snippet")
        resource = snippet.get("resourceId") if isinstance(snippet, dict) else None
        video_id = resource.get("videoId") if isinstance(resource, dict) else None
        if isinstance(video_id, str):
            video_ids.append(video_id)
    if not video_ids:
        return playlist_items

    async with httpx.AsyncClient(timeout=15.0) as client:
        videos_response = await client.get(
            YOUTUBE_VIDEOS_URL,
            params={
                "part": "statistics",
                "key": settings.YOUTUBE_API_KEY,
                "id": ",".join(video_ids),
            },
        )
        videos_response.raise_for_status()
        videos_payload = videos_response.json()

    videos = videos_payload.get("items")
    view_counts: dict[str, int] = {}
    if isinstance(videos, list):
        for video in videos:
            if not isinstance(video, dict):
                continue
            video_id = video.get("id")
            statistics = video.get("statistics")
            if isinstance(video_id, str) and isinstance(statistics, dict):
                view_counts[video_id] = _parse_view_count(statistics.get("viewCount"))
    for item in playlist_items:
        snippet = item.get("snippet")
        resource = snippet.get("resourceId") if isinstance(snippet, dict) else None
        video_id = resource.get("videoId") if isinstance(resource, dict) else None
        if isinstance(video_id, str):
            item["view_count"] = view_counts.get(video_id, 0)
    return playlist_items


async def fetch_youtube_channel_id(account_identifier: str) -> str:
    if not settings.YOUTUBE_API_KEY:
        raise RuntimeError("YouTube media sync credentials are not configured")

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            YOUTUBE_CHANNELS_URL,
            params={
                "part": "id",
                "key": settings.YOUTUBE_API_KEY,
                **_youtube_channel_params(account_identifier),
            },
        )
        response.raise_for_status()
    payload = response.json()
    items = payload.get("items")
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        raise ValueError("YouTube channel was not found")
    channel_id = items[0].get("id")
    if not isinstance(channel_id, str) or not channel_id:
        raise ValueError("YouTube channel API returned an invalid payload")
    return channel_id


async def refresh_youtube_websub_subscriptions(
    *, links: list[PlayerSocialLink] | None = None
) -> bool:
    if not youtube_websub_is_configured():
        return True

    if links is None:
        async with async_session_maker() as session:
            links = list(
                (
                    await session.exec(
                        select(PlayerSocialLink).where(
                            col(PlayerSocialLink.platform)
                            == PlayerSocialPlatform.YOUTUBE,
                            col(PlayerSocialLink.verified).is_(True),
                        )
                    )
                ).all()
            )

    success = True
    async with httpx.AsyncClient(timeout=15.0) as client:
        for link in links:
            try:
                channel_id = await fetch_youtube_channel_id(link.account_identifier)
                response = await client.post(
                    YOUTUBE_WEBSUB_HUB_URL,
                    data={
                        "hub.mode": "subscribe",
                        "hub.topic": f"{YOUTUBE_WEBSUB_TOPIC_URL}?channel_id={channel_id}",
                        "hub.callback": youtube_websub_callback_url(),
                        "hub.verify": "async",
                        "hub.secret": settings.YOUTUBE_WEBSUB_SECRET,
                        "hub.lease_seconds": str(YOUTUBE_WEBSUB_LEASE_SECONDS),
                    },
                )
                response.raise_for_status()
            except Exception:
                success = False
                logger.exception(
                    "Failed to refresh YouTube WebSub subscription",
                    extra={"social_link_id": str(link.id)},
                )
    return success


def schedule_youtube_media_sync() -> None:
    task = asyncio.create_task(sync_youtube_media_once())

    def log_failure(completed_task: asyncio.Task[int]) -> None:
        try:
            completed_task.result()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("YouTube media webhook sync failed")

    task.add_done_callback(log_failure)


async def cache_youtube_thumbnail(*, video_id: str, raw_url: str | None) -> str | None:
    if raw_url is None:
        return None
    if not r2_storage.is_configured():
        return raw_url
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(raw_url, follow_redirects=True)
            response.raise_for_status()
        content_type = response.headers.get("content-type", "image/jpeg").split(";", 1)[
            0
        ]
        if not content_type.startswith("image/"):
            raise ValueError("YouTube thumbnail was not an image")
        return cast(
            str,
            await r2_storage.put_object(
                key=f"media/thumbnails/youtube/{video_id}.jpg",
                body=response.content,
                content_type=content_type,
                cache_control="public, max-age=31536000, immutable",
            ),
        )
    except Exception:
        logger.exception(
            "Failed to cache YouTube thumbnail", extra={"video_id": video_id}
        )
        return raw_url


async def sync_youtube_media_once(session: AsyncSession | None = None) -> int:
    managed = session is None
    if managed:
        session = async_session_maker()
    assert session is not None

    now = get_datetime_utc()
    cutoff = now - timedelta(days=MEDIA_RETENTION_DAYS)
    links = list(
        (
            await session.exec(
                select(PlayerSocialLink).where(
                    col(PlayerSocialLink.platform) == PlayerSocialPlatform.YOUTUBE,
                    col(PlayerSocialLink.verified).is_(True),
                )
            )
        ).all()
    )
    changed = 0
    try:
        for link in links:
            try:
                entries = await fetch_youtube_posts(link.account_identifier)
                for item in entries:
                    snippet = item.get("snippet")
                    content_details = item.get("contentDetails")
                    if not isinstance(snippet, dict) or not isinstance(
                        content_details, dict
                    ):
                        continue
                    resource = snippet.get("resourceId")
                    video_id = (
                        resource.get("videoId") if isinstance(resource, dict) else None
                    )
                    published_at = _parse_published(
                        content_details.get("videoPublishedAt")
                    )
                    if (
                        not isinstance(video_id, str)
                        or not video_id
                        or published_at is None
                        or published_at < cutoff
                    ):
                        continue
                    thumbnail_url = await cache_youtube_thumbnail(
                        video_id=video_id,
                        raw_url=_thumbnail_url(snippet),
                    )
                    values = {
                        "player_social_link_id": link.id,
                        "player_steamid64": link.player_steamid64,
                        "platform": PlayerSocialPlatform.YOUTUBE,
                        "external_video_id": video_id,
                        "title": str(snippet.get("title") or "Untitled video")[:500],
                        "description": str(snippet.get("description") or "")[:10000]
                        or None,
                        "url": f"https://www.youtube.com/watch?v={video_id}",
                        "thumbnail_url": thumbnail_url,
                        "published_at": published_at,
                        "view_count": _parse_view_count(item.get("view_count")),
                        "discovered_at": now,
                        "duration_seconds": None,
                        "available": True,
                        "last_checked_at": now,
                        "last_error": None,
                    }
                    statement = (
                        pg_insert(MediaPost.__table__)  # type: ignore[attr-defined]
                        .values(values)
                        .on_conflict_do_update(
                            index_elements=["platform", "external_video_id"],
                            set_={
                                key: values[key]
                                for key in (
                                    "player_social_link_id",
                                    "player_steamid64",
                                    "title",
                                    "description",
                                    "url",
                                    "thumbnail_url",
                                    "published_at",
                                    "view_count",
                                    "duration_seconds",
                                    "available",
                                    "last_checked_at",
                                    "last_error",
                                )
                            },
                        )
                    )
                    await session.exec(statement)
                    changed += 1
            except Exception as exc:
                logger.warning(
                    "YouTube media sync failed",
                    extra={"social_link_id": str(link.id), "error": str(exc)[:500]},
                )
        await session.commit()
        await crud.prune_media_posts(session=session, before=cutoff)
    finally:
        if managed:
            await session.close()
    return changed


async def run_media_sync_runner_in_app() -> None:
    next_websub_refresh_at: datetime | None = None
    while True:
        try:
            database_uri = str(settings.SQLALCHEMY_DATABASE_URI).replace(
                "postgresql+psycopg", "postgresql", 1
            )
            async with await psycopg.AsyncConnection.connect(
                database_uri, autocommit=True
            ) as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute(
                        "SELECT pg_try_advisory_lock(%s)", (MEDIA_SYNC_LOCK_ID,)
                    )
                    row = await cursor.fetchone()
                if not row or row[0] is not True:
                    await asyncio.sleep(settings.MEDIA_SYNC_POLL_SECONDS)
                    continue
                try:
                    while True:
                        await sync_youtube_media_once()
                        now = get_datetime_utc()
                        if (
                            next_websub_refresh_at is None
                            or now >= next_websub_refresh_at
                        ):
                            websub_refresh_succeeded = (
                                await refresh_youtube_websub_subscriptions()
                            )
                            next_websub_refresh_at = now + timedelta(
                                seconds=(
                                    YOUTUBE_WEBSUB_RENEWAL_SECONDS
                                    if websub_refresh_succeeded
                                    else YOUTUBE_WEBSUB_FAILURE_RETRY_SECONDS
                                )
                            )
                        await asyncio.sleep(settings.MEDIA_SYNC_POLL_SECONDS)
                finally:
                    with suppress(Exception):
                        async with connection.cursor() as cursor:
                            await cursor.execute(
                                "SELECT pg_advisory_unlock(%s)", (MEDIA_SYNC_LOCK_ID,)
                            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("YouTube media runner failed")
            await asyncio.sleep(1)


async def stop_media_sync_runner(task: asyncio.Task[None] | None) -> None:
    if task is None:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
