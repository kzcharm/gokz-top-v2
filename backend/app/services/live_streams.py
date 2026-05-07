from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx
import psycopg
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.core.db import async_session_maker
from app.models import PlayerSocialPlatform, get_datetime_utc
from app.services.player_social_links import build_player_social_link_url

ENABLED_LIVE_STREAM_PLATFORMS: tuple[PlayerSocialPlatform, ...] = (
    PlayerSocialPlatform.BILIBILI,
)
BILIBILI_PREVIEW_HOST_SUFFIXES = ("hdslb.com",)
LIVE_STREAM_RUNNER_LOCK_ID = int.from_bytes(
    hashlib.sha256(b"gokz-top-v2:live-stream-runner").digest()[:8],
    byteorder="big",
    signed=True,
)


@dataclass(frozen=True, slots=True)
class BilibiliLiveStatus:
    is_live: bool
    stream_title: str | None = None
    viewer_count: int | None = None
    preview_image_url: str | None = None
    stream_url: str | None = None
    channel_display_name: str | None = None
    started_at: datetime | None = None


def get_live_stream_stale_after() -> timedelta:
    return timedelta(seconds=max(settings.LIVE_STREAM_POLL_SECONDS * 3, 60))


def build_live_preview_proxy_url(raw_url: str) -> str:
    encoded_url = urlencode({"url": raw_url})
    return f"{settings.API_V1_STR}/live/preview-image?{encoded_url}"


def resolve_live_preview_url(raw_url: str) -> str:
    return build_live_preview_proxy_url(raw_url) if is_allowed_live_preview_url(raw_url) else raw_url


def is_allowed_live_preview_url(url: str) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme != "https":
        return False
    host = parsed.netloc.split(":", maxsplit=1)[0].lower()
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in BILIBILI_PREVIEW_HOST_SUFFIXES)


async def fetch_live_preview_image(url: str) -> tuple[bytes, str]:
    if not is_allowed_live_preview_url(url):
        raise ValueError("Preview URL host is not allowed")

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        media_type = response.headers.get("content-type", "image/jpeg")
        return response.content, media_type


def _psycopg_database_uri() -> str:
    return str(settings.SQLALCHEMY_DATABASE_URI).replace(
        "postgresql+psycopg",
        "postgresql",
        1,
    )


def _parse_bilibili_started_at(value: object | None) -> datetime | None:
    if not value:
        return None

    if isinstance(value, int | float):
        if value <= 0:
            return None
        try:
            return datetime.fromtimestamp(value, tz=UTC)
        except (OSError, OverflowError, ValueError):
            return None

    if not isinstance(value, str):
        return None

    normalized = value.strip()
    if not normalized or normalized in {"0000-00-00 00:00:00", "0000-00-00"}:
        return None

    try:
        return datetime.strptime(normalized, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=UTC
        )
    except ValueError:
        return None


async def check_bilibili_live_status(
    uids: Sequence[int],
) -> dict[int, BilibiliLiveStatus]:
    if not uids:
        return {}

    result = {
        uid: BilibiliLiveStatus(is_live=False)
        for uid in uids
    }
    response_data = await _fetch_bilibili_live_status_payload(list(uids))
    for uid_str, info in response_data.items():
        try:
            uid = int(uid_str)
        except (TypeError, ValueError):
            continue
        if uid not in result:
            continue

        live_status = info.get("live_status", 0)
        if live_status != 1:
            continue

        room_id = info.get("room_id")
        stream_url = f"https://live.bilibili.com/{room_id}" if room_id else None
        result[uid] = BilibiliLiveStatus(
            is_live=True,
            stream_title=info.get("title"),
            viewer_count=info.get("online"),
            preview_image_url=info.get("cover_from_user"),
            stream_url=stream_url,
            channel_display_name=info.get("uname"),
            started_at=_parse_bilibili_started_at(info.get("live_time")),
        )
    return result


async def _fetch_bilibili_live_status_payload(uids: list[int]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            "https://api.live.bilibili.com/room/v1/Room/get_status_info_by_uids",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/91.0.4472.124 Safari/537.36"
                ),
                "Content-Type": "application/json",
            },
            json={"uids": uids},
        )
        response.raise_for_status()
        payload = response.json()
    if payload.get("code") != 0:
        raise ValueError(payload.get("msg") or "Bilibili live API error")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("Bilibili live API returned an invalid payload")
    return data


async def refresh_live_streams_once(
    *,
    session: AsyncSession | None = None,
) -> int:
    if session is not None:
        return await _refresh_live_streams_with_session(session)

    async with async_session_maker() as managed_session:
        return await _refresh_live_streams_with_session(managed_session)


async def _refresh_live_streams_with_session(session: AsyncSession) -> int:
    links = await crud.list_verified_live_stream_links(
        session=session,
        platforms=ENABLED_LIVE_STREAM_PLATFORMS,
    )
    if not links:
        return 0

    bilibili_links = [
        link for link in links if link.platform == PlayerSocialPlatform.BILIBILI
    ]
    statuses = await check_bilibili_live_status(
        [int(link.account_identifier) for link in bilibili_links]
    )
    checked_at = get_datetime_utc()
    for link in bilibili_links:
        status = statuses.get(int(link.account_identifier), BilibiliLiveStatus(False))
        await crud.upsert_live_stream_state(
            session=session,
            social_link_id=link.id,
            checked_at=checked_at,
            is_live=status.is_live,
            stream_url=(
                status.stream_url
                or build_player_social_link_url(
                    platform=link.platform,
                    account_identifier=link.account_identifier,
                )
            ),
            stream_title=status.stream_title,
            preview_image_url=status.preview_image_url,
            channel_display_name=status.channel_display_name,
            viewer_count=status.viewer_count,
            started_at=status.started_at,
            commit=False,
        )
    await session.commit()
    return len(bilibili_links)


async def run_live_stream_runner_in_app() -> None:
    while True:
        try:
            async with await psycopg.AsyncConnection.connect(
                _psycopg_database_uri(),
                autocommit=True,
            ) as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute(
                        "SELECT pg_try_advisory_lock(%s)",
                        (LIVE_STREAM_RUNNER_LOCK_ID,),
                    )
                    row = await cursor.fetchone()
                if not row or row[0] is not True:
                    await asyncio.sleep(settings.LIVE_STREAM_POLL_SECONDS)
                    continue

                try:
                    while True:
                        await refresh_live_streams_once()
                        await asyncio.sleep(settings.LIVE_STREAM_POLL_SECONDS)
                finally:
                    with suppress(Exception):
                        async with connection.cursor() as cursor:
                            await cursor.execute(
                                "SELECT pg_advisory_unlock(%s)",
                                (LIVE_STREAM_RUNNER_LOCK_ID,),
                            )
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(1)


async def stop_live_stream_runner(
    task: asyncio.Task[None] | None,
) -> None:
    if task is None:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
