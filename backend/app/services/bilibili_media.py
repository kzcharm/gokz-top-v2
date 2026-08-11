from __future__ import annotations

import asyncio
import hashlib
import logging
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Any

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
MEDIA_SYNC_LOCK_ID = int.from_bytes(hashlib.sha256(b"gokz-top-v2:media-runner").digest()[:8], "big", signed=True)
BILIBILI_MEDIA_RETENTION_DAYS = 90


def _parse_duration(value: object) -> int | None:
    if isinstance(value, int | float):
        return max(0, int(value))
    if isinstance(value, str):
        parts = value.split(":")
        if parts and all(part.isdecimal() for part in parts):
            try:
                total = 0
                for part in parts:
                    total = total * 60 + int(part)
                return total
            except ValueError:
                return None
    return None


def _parse_published(value: object) -> datetime | None:
    if isinstance(value, int | float) and value > 0:
        return datetime.fromtimestamp(value, tz=UTC)
    return None


async def fetch_bilibili_posts(uid: int, *, page_size: int = 30) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=15, headers={"User-Agent": "Mozilla/5.0"}) as client:
        response = await client.get(
            "https://api.bilibili.com/x/space/arc/search",
            params={"mid": uid, "pn": 1, "ps": page_size, "order": "pubdate"},
        )
        response.raise_for_status()
        payload = response.json()
    if payload.get("code") != 0:
        raise ValueError(payload.get("message") or "Bilibili media API error")
    data = payload.get("data") or {}
    archive = data.get("list") if isinstance(data, dict) else None
    videos = archive.get("vlist") if isinstance(archive, dict) else None
    return [item for item in videos if isinstance(item, dict)] if isinstance(videos, list) else []


async def cache_bilibili_thumbnail(*, bvid: str, raw_url: object) -> str | None:
    if not isinstance(raw_url, str) or not raw_url:
        return None
    source_url = f"https:{raw_url}" if raw_url.startswith("//") else raw_url
    if not r2_storage.is_configured() or not source_url.startswith("https://"):
        return source_url
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(source_url, follow_redirects=True)
            response.raise_for_status()
        content_type = response.headers.get("content-type", "image/jpeg").split(";", 1)[0]
        if not content_type.startswith("image/"):
            raise ValueError("Bilibili thumbnail was not an image")
        return await r2_storage.put_object(
            key=f"media/thumbnails/bilibili/{bvid}.jpg",
            body=response.content,
            content_type=content_type,
            cache_control="public, max-age=31536000, immutable",
        )
    except Exception:
        logger.exception("Failed to cache Bilibili thumbnail", extra={"bvid": bvid})
        return source_url


async def sync_bilibili_media_once(session: AsyncSession | None = None) -> int:
    managed = session is None
    if managed:
        session = async_session_maker()
    assert session is not None
    now = get_datetime_utc()
    cutoff = now - timedelta(days=BILIBILI_MEDIA_RETENTION_DAYS)
    links = list((await session.exec(select(PlayerSocialLink).where(
        col(PlayerSocialLink.platform) == PlayerSocialPlatform.BILIBILI,
        col(PlayerSocialLink.verified).is_(True),
    ))).all())
    changed = 0
    try:
        for link in links:
            try:
                entries = await fetch_bilibili_posts(int(link.account_identifier))
                for item in entries:
                    published_at = _parse_published(item.get("created"))
                    bvid = item.get("bvid")
                    if published_at is None or not isinstance(bvid, str) or published_at < cutoff:
                        continue
                    title = str(item.get("title") or "Untitled video")[:500]
                    thumbnail_url = await cache_bilibili_thumbnail(
                        bvid=bvid, raw_url=item.get("pic")
                    )
                    values = {
                        "player_social_link_id": link.id,
                        "player_steamid64": link.player_steamid64,
                        "platform": PlayerSocialPlatform.BILIBILI,
                        "external_video_id": bvid,
                        "title": title,
                        "description": str(item.get("description") or "")[:10000] or None,
                        "url": f"https://www.bilibili.com/video/{bvid}",
                        "thumbnail_url": thumbnail_url,
                        "published_at": published_at,
                        "discovered_at": now,
                        "duration_seconds": _parse_duration(item.get("length")),
                        "available": True,
                        "last_checked_at": now,
                        "last_error": None,
                    }
                    statement = pg_insert(MediaPost.__table__).values(values).on_conflict_do_update(
                        index_elements=["platform", "external_video_id"],
                        set_={key: values[key] for key in ("player_social_link_id", "player_steamid64", "title", "description", "url", "thumbnail_url", "published_at", "duration_seconds", "available", "last_checked_at", "last_error")},
                    )
                    await session.exec(statement)
                    changed += 1
            except Exception as exc:
                logger.warning("Bilibili media sync failed", extra={"social_link_id": str(link.id), "error": str(exc)[:500]})
        await session.commit()
        await crud.prune_media_posts(session=session, before=cutoff)
    finally:
        if managed:
            await session.close()
    return changed


async def run_media_sync_runner_in_app() -> None:
    while True:
        try:
            database_uri = str(settings.SQLALCHEMY_DATABASE_URI).replace(
                "postgresql+psycopg", "postgresql", 1
            )
            async with await psycopg.AsyncConnection.connect(database_uri, autocommit=True) as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute("SELECT pg_try_advisory_lock(%s)", (MEDIA_SYNC_LOCK_ID,))
                    row = await cursor.fetchone()
                if not row or row[0] is not True:
                    await asyncio.sleep(settings.MEDIA_SYNC_POLL_SECONDS)
                    continue
                try:
                    while True:
                        await sync_bilibili_media_once()
                        await asyncio.sleep(settings.MEDIA_SYNC_POLL_SECONDS)
                finally:
                    with suppress(Exception):
                        async with connection.cursor() as cursor:
                            await cursor.execute("SELECT pg_advisory_unlock(%s)", (MEDIA_SYNC_LOCK_ID,))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Bilibili media runner failed")
            await asyncio.sleep(1)


async def stop_media_sync_runner(task: asyncio.Task[None] | None) -> None:
    if task is None:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
