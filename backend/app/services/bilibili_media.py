from __future__ import annotations

import hashlib
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from urllib.parse import urlencode, urlparse

import httpx
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
BILIBILI_MEDIA_RETENTION_DAYS = 90
BILIBILI_WBI_KEYS_URL = "https://api.bilibili.com/x/web-interface/nav"
BILIBILI_UPLOADS_URL = "https://api.bilibili.com/x/space/wbi/arc/search"
BILIBILI_VIDEO_VIEW_URL = "https://api.bilibili.com/x/web-interface/view"
BILIBILI_WBI_CACHE_TTL = timedelta(minutes=10)
_BILIBILI_BROWSER_HEADERS = {
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://space.bilibili.com/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
}
_WBI_MIXIN_KEY_ENC_TAB = (
    46,
    47,
    18,
    2,
    53,
    8,
    23,
    32,
    15,
    50,
    10,
    31,
    58,
    3,
    45,
    35,
    27,
    43,
    5,
    49,
    33,
    9,
    42,
    19,
    29,
    28,
    14,
    39,
    12,
    38,
    41,
    13,
    37,
    48,
    7,
    16,
    24,
    55,
    40,
    61,
    26,
    17,
    0,
    1,
    60,
    51,
    30,
    4,
    22,
    25,
    54,
    21,
    56,
    59,
    6,
    63,
    57,
    62,
    11,
    36,
    20,
    34,
    44,
    52,
)
_WBI_SANITIZE_CHARS = "!'()*"
_wbi_keys: tuple[str, str] | None = None
_wbi_keys_fetched_at: datetime | None = None


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


def _bilibili_headers() -> dict[str, str]:
    headers = dict(_BILIBILI_BROWSER_HEADERS)
    if settings.BILIBILI_COOKIE:
        headers["Cookie"] = settings.BILIBILI_COOKIE
    return headers


def _extract_wbi_key(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Bilibili WBI key URL was invalid")
    filename = urlparse(value).path.rsplit("/", 1)[-1]
    key, separator, _ = filename.partition(".")
    if not separator or not key:
        raise ValueError("Bilibili WBI key URL was invalid")
    return key


def _build_wbi_mixin_key(img_key: str, sub_key: str) -> str:
    source = img_key + sub_key
    mixed = "".join(
        source[index] for index in _WBI_MIXIN_KEY_ENC_TAB if index < len(source)
    )
    if len(mixed) < 32:
        raise ValueError("Bilibili WBI key was invalid")
    return mixed[:32]


def _sign_wbi_params(
    params: dict[str, str | int],
    *,
    img_key: str,
    sub_key: str,
    wts: int | None = None,
) -> dict[str, str]:
    signed = {
        key: "".join(
            character
            for character in str(value)
            if character not in _WBI_SANITIZE_CHARS
        )
        for key, value in params.items()
    }
    signed["wts"] = str(wts if wts is not None else int(time.time()))
    query = urlencode(sorted(signed.items()))
    signed["w_rid"] = hashlib.md5(
        f"{query}{_build_wbi_mixin_key(img_key, sub_key)}".encode()
    ).hexdigest()
    return signed


async def _fetch_wbi_keys(client: httpx.AsyncClient) -> tuple[str, str]:
    response = await client.get(BILIBILI_WBI_KEYS_URL)
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise ValueError(payload.get("message") or "Bilibili WBI key API error")
    data = payload.get("data")
    wbi_image = data.get("wbi_img") if isinstance(data, dict) else None
    if not isinstance(wbi_image, dict):
        raise ValueError("Bilibili WBI key API returned an invalid payload")
    return _extract_wbi_key(wbi_image.get("img_url")), _extract_wbi_key(
        wbi_image.get("sub_url")
    )


async def _get_wbi_keys(
    client: httpx.AsyncClient, *, force_refresh: bool = False
) -> tuple[str, str]:
    global _wbi_keys, _wbi_keys_fetched_at

    now = datetime.now(UTC)
    if (
        not force_refresh
        and _wbi_keys is not None
        and _wbi_keys_fetched_at is not None
        and now - _wbi_keys_fetched_at < BILIBILI_WBI_CACHE_TTL
    ):
        return _wbi_keys
    _wbi_keys = await _fetch_wbi_keys(client)
    _wbi_keys_fetched_at = now
    return _wbi_keys


def _is_retryable_bilibili_response(
    response: httpx.Response, payload: dict[str, Any]
) -> bool:
    return response.status_code in {412, 429} or payload.get("code") in {
        -352,
        -412,
        -799,
    }


async def _fetch_bilibili_upload_page(
    client: httpx.AsyncClient, *, uid: int, page: int, page_size: int
) -> tuple[list[dict[str, Any]], int | None]:
    for attempt in range(2):
        img_key, sub_key = await _get_wbi_keys(client, force_refresh=attempt == 1)
        response = await client.get(
            BILIBILI_UPLOADS_URL,
            params=_sign_wbi_params(
                {"mid": uid, "pn": page, "ps": page_size, "order": "pubdate"},
                img_key=img_key,
                sub_key=sub_key,
            ),
        )
        payload = response.json()
        if attempt == 0 and _is_retryable_bilibili_response(response, payload):
            continue
        response.raise_for_status()
        if payload.get("code") != 0:
            raise ValueError(payload.get("message") or "Bilibili media API error")
        data = payload.get("data")
        archive = data.get("list") if isinstance(data, dict) else None
        videos = archive.get("vlist") if isinstance(archive, dict) else None
        page_data = data.get("page") if isinstance(data, dict) else None
        total = page_data.get("count") if isinstance(page_data, dict) else None
        return (
            [item for item in videos if isinstance(item, dict)]
            if isinstance(videos, list)
            else [],
            total if isinstance(total, int) and total >= 0 else None,
        )
    raise AssertionError("Bilibili upload page retry loop was exhausted")


async def fetch_bilibili_posts(
    uid: int,
    *,
    page_size: int = 30,
    cutoff: datetime | None = None,
) -> list[dict[str, Any]]:
    posts: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=15.0, headers=_bilibili_headers()) as client:
        page = 1
        total: int | None = None
        while total is None or (page - 1) * page_size < total:
            entries, total = await _fetch_bilibili_upload_page(
                client, uid=uid, page=page, page_size=page_size
            )
            if not entries:
                break
            posts.extend(entries)
            if cutoff is not None and any(
                (published_at := _parse_published(entry.get("created"))) is not None
                and published_at < cutoff
                for entry in entries
            ):
                break
            page += 1
    return posts


async def fetch_bilibili_video_view_counts(video_ids: list[str]) -> dict[str, int]:
    view_counts: dict[str, int] = {}
    async with httpx.AsyncClient(timeout=15.0, headers=_bilibili_headers()) as client:
        for video_id in video_ids:
            response = await client.get(
                BILIBILI_VIDEO_VIEW_URL, params={"bvid": video_id}
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") != 0:
                raise ValueError(payload.get("message") or "Bilibili video API error")
            data = payload.get("data")
            statistics = data.get("stat") if isinstance(data, dict) else None
            view_count = (
                statistics.get("view") if isinstance(statistics, dict) else None
            )
            if isinstance(view_count, int) and view_count >= 0:
                view_counts[video_id] = view_count
    return view_counts


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
        content_type = response.headers.get("content-type", "image/jpeg").split(";", 1)[
            0
        ]
        if not content_type.startswith("image/"):
            raise ValueError("Bilibili thumbnail was not an image")
        return cast(
            str,
            await r2_storage.put_object(
                key=f"media/thumbnails/bilibili/{bvid}.jpg",
                body=response.content,
                content_type=content_type,
                cache_control="public, max-age=31536000, immutable",
            ),
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
    links = list(
        (
            await session.exec(
                select(PlayerSocialLink).where(
                    col(PlayerSocialLink.platform) == PlayerSocialPlatform.BILIBILI,
                    col(PlayerSocialLink.verified).is_(True),
                )
            )
        ).all()
    )
    changed = 0
    try:
        for link in links:
            try:
                entries = await fetch_bilibili_posts(
                    int(link.account_identifier), cutoff=cutoff
                )
                for item in entries:
                    published_at = _parse_published(item.get("created"))
                    bvid = item.get("bvid")
                    if (
                        published_at is None
                        or not isinstance(bvid, str)
                        or published_at < cutoff
                    ):
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
                        "description": str(item.get("description") or "")[:10000]
                        or None,
                        "url": f"https://www.bilibili.com/video/{bvid}",
                        "thumbnail_url": thumbnail_url,
                        "published_at": published_at,
                        "discovered_at": now,
                        "duration_seconds": _parse_duration(item.get("length")),
                        "available": True,
                        "last_checked_at": now,
                        "last_error": None,
                    }
                    statement = (
                        pg_insert(MediaPost.__table__)
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
                    "Bilibili media sync failed",
                    extra={"social_link_id": str(link.id), "error": str(exc)[:500]},
                )
        await session.commit()
        await crud.prune_media_posts(session=session, before=cutoff)
    finally:
        if managed:
            await session.close()
    return changed
