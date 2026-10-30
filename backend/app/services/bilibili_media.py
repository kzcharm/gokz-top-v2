from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlencode, urlparse, urlsplit

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
from app.services.media_classifier import classify_media_post

logger = logging.getLogger(__name__)
BILIBILI_MEDIA_RETENTION_DAYS = 90
BILIBILI_WBI_KEYS_URL = "https://api.bilibili.com/x/web-interface/nav"
BILIBILI_UPLOADS_URL = "https://api.bilibili.com/x/space/wbi/arc/search"
BILIBILI_VIDEO_VIEW_URL = "https://api.bilibili.com/x/web-interface/view"
BILIBILI_VIDEO_TAGS_URL = "https://api.bilibili.com/x/tag/archive/tags"
BILIBILI_WBI_CACHE_TTL = timedelta(minutes=10)
BILIBILI_THUMBNAIL_HOST_SUFFIXES = ("hdslb.com",)
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


BILIBILI_METADATA_TTL = timedelta(hours=24)
BILIBILI_BACKOFF_INITIAL_SECONDS = 900
BILIBILI_BACKOFF_MAX_SECONDS = 21_600


@dataclass
class _RequestBackoff:
    failures: int
    retry_at: datetime


class BilibiliBackoffError(RuntimeError):
    """An endpoint is paused after a Bilibili anti-bot or rate-limit response."""


# Endpoint-specific: blocked video details must not stop upload discovery.
# Shared by polling, manual reclassification and on-demand view-count refreshes.
_request_backoffs: dict[str, _RequestBackoff] = {}


def _check_backoff(url: str) -> None:
    state = _request_backoffs.get(url)
    if state is not None and get_datetime_utc() < state.retry_at:
        raise BilibiliBackoffError(
            f"Bilibili endpoint paused until {state.retry_at.isoformat()}: {url}"
        )


def _start_backoff(url: str, response: httpx.Response) -> None:
    now = get_datetime_utc()
    previous = _request_backoffs.get(url)
    failures = previous.failures + 1 if previous else 1
    seconds = min(
        BILIBILI_BACKOFF_MAX_SECONDS,
        BILIBILI_BACKOFF_INITIAL_SECONDS * 2 ** min(failures - 1, 5),
    )
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            seconds = max(seconds, int(retry_after))
        except ValueError:
            try:
                retry_date = parsedate_to_datetime(retry_after)
                seconds = max(seconds, int((retry_date - now).total_seconds()))
            except (TypeError, ValueError, OverflowError):
                pass
    state = _RequestBackoff(
        failures=failures, retry_at=now + timedelta(seconds=seconds)
    )
    _request_backoffs[url] = state
    logger.warning(
        "Bilibili endpoint %s backed off until %s after %s rejection(s)",
        url,
        state.retry_at.isoformat(),
        failures,
        extra={
            "endpoint": url,
            "retry_at": state.retry_at.isoformat(),
            "failures": failures,
        },
    )
    raise BilibiliBackoffError(
        f"Bilibili endpoint rejected requests; paused until {state.retry_at.isoformat()}: {url}"
    )


async def _get_json(
    client: httpx.AsyncClient, url: str, *, params: dict[str, str] | None = None
) -> dict[str, Any]:
    _check_backoff(url)
    response = await client.get(url, params=params)
    # Check status before parsing: HTTP 412 may return HTML rather than JSON.
    if response.status_code in {412, 429}:
        _start_backoff(url, response)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Bilibili API returned an invalid payload")
    if payload.get("code") in {-352, -412, -799}:
        _start_backoff(url, response)
    if payload.get("code") != 0:
        raise ValueError(payload.get("message") or "Bilibili API error")
    _request_backoffs.pop(url, None)
    return payload


def _metadata_is_fresh(post: MediaPost, item: dict[str, Any], now: datetime) -> bool:
    """Upload descriptions can be truncated; compare them as canonical prefixes."""
    title = item.get("title")
    description = item.get("description")
    duration = _parse_duration(item.get("length") or item.get("duration"))
    return (
        post.metadata_checked_at is not None
        and now - post.metadata_checked_at < BILIBILI_METADATA_TTL
        and (not isinstance(title, str) or title[:500] == post.title)
        and (
            not isinstance(description, str)
            or (post.description or "").startswith(description)
        )
        and (duration is None or duration == post.duration_seconds)
    )


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


def _parse_view_count(value: object) -> int:
    if isinstance(value, int | float):
        return max(0, int(value))
    if isinstance(value, str):
        try:
            return max(0, int(value))
        except ValueError:
            return 0
    return 0


def _bilibili_headers() -> dict[str, str]:
    headers = dict(_BILIBILI_BROWSER_HEADERS)
    if settings.BILIBILI_COOKIE:
        headers["Cookie"] = settings.BILIBILI_COOKIE
    return headers


def is_allowed_bilibili_thumbnail_url(url: str) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    host = parsed.hostname
    if host is None:
        return False
    return any(
        host == suffix or host.endswith(f".{suffix}")
        for suffix in BILIBILI_THUMBNAIL_HOST_SUFFIXES
    )


async def fetch_bilibili_thumbnail(url: str) -> tuple[bytes, str]:
    if not is_allowed_bilibili_thumbnail_url(url):
        raise ValueError("Bilibili thumbnail URL host is not allowed")

    async with httpx.AsyncClient(
        timeout=15.0,
        follow_redirects=True,
        headers=_bilibili_headers(),
    ) as client:
        response = await client.get(url)
        response.raise_for_status()

    if not is_allowed_bilibili_thumbnail_url(str(response.url)):
        raise ValueError("Bilibili thumbnail redirected to an untrusted host")
    media_type = response.headers.get("content-type", "image/jpeg").split(";", 1)[0]
    if not media_type.startswith("image/"):
        raise ValueError("Bilibili thumbnail was not an image")
    return response.content, media_type


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
    payload = await _get_json(client, BILIBILI_WBI_KEYS_URL)
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


async def _fetch_bilibili_upload_page(
    client: httpx.AsyncClient, *, uid: int, page: int, page_size: int
) -> tuple[list[dict[str, Any]], int | None]:
    _check_backoff(BILIBILI_UPLOADS_URL)
    img_key, sub_key = await _get_wbi_keys(client)
    payload = await _get_json(
        client,
        BILIBILI_UPLOADS_URL,
        params=_sign_wbi_params(
            {"mid": uid, "pn": page, "ps": page_size, "order": "pubdate"},
            img_key=img_key,
            sub_key=sub_key,
        ),
    )
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


async def fetch_bilibili_posts(
    uid: int,
    *,
    page_size: int = 30,
    cutoff: datetime | None = None,
) -> list[dict[str, Any]]:
    _check_backoff(BILIBILI_UPLOADS_URL)
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
    _check_backoff(BILIBILI_VIDEO_VIEW_URL)
    view_counts: dict[str, int] = {}
    async with httpx.AsyncClient(timeout=15.0, headers=_bilibili_headers()) as client:
        for video_id in video_ids:
            payload = await _get_json(
                client, BILIBILI_VIDEO_VIEW_URL, params={"bvid": video_id}
            )
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


async def fetch_bilibili_video_detail(bvid: str) -> dict[str, Any]:
    _check_backoff(BILIBILI_VIDEO_VIEW_URL)
    async with httpx.AsyncClient(timeout=15.0, headers=_bilibili_headers()) as client:
        payload = await _get_json(
            client, BILIBILI_VIDEO_VIEW_URL, params={"bvid": bvid}
        )
    if payload.get("code") != 0:
        raise ValueError(payload.get("message") or "Bilibili video API error")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("Bilibili video API returned an invalid payload")
    return data


async def fetch_bilibili_video_tags(bvid: str) -> list[str]:
    _check_backoff(BILIBILI_VIDEO_TAGS_URL)
    async with httpx.AsyncClient(timeout=15.0, headers=_bilibili_headers()) as client:
        payload = await _get_json(
            client, BILIBILI_VIDEO_TAGS_URL, params={"bvid": bvid}
        )
    if payload.get("code") != 0:
        raise ValueError(payload.get("message") or "Bilibili tag API error")
    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError("Bilibili tag API returned an invalid payload")
    return [
        tag_name
        for item in data
        if isinstance(item, dict)
        and isinstance((tag_name := item.get("tag_name")), str)
    ]


async def cache_bilibili_thumbnail(*, bvid: str, raw_url: object) -> str | None:
    if not isinstance(raw_url, str) or not raw_url:
        return None
    source_url = f"https:{raw_url}" if raw_url.startswith("//") else raw_url
    if not r2_storage.is_configured() or not is_allowed_bilibili_thumbnail_url(
        source_url
    ):
        return source_url
    try:
        content, content_type = await fetch_bilibili_thumbnail(source_url)
        return await r2_storage.put_object(
            key=f"media/thumbnails/bilibili/{bvid}.jpg",
            body=content,
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
                entry_ids = [
                    bvid
                    for item in entries
                    if isinstance((bvid := item.get("bvid")), str)
                ]
                existing_posts = {
                    post.external_video_id: post
                    for post in (
                        await session.exec(
                            select(MediaPost).where(
                                col(MediaPost.platform)
                                == PlayerSocialPlatform.BILIBILI,
                                col(MediaPost.external_video_id).in_(entry_ids),
                            )
                        )
                    ).all()
                }
                for item in entries:
                    published_at = _parse_published(item.get("created"))
                    bvid = item.get("bvid")
                    if (
                        published_at is None
                        or not isinstance(bvid, str)
                        or published_at < cutoff
                    ):
                        continue
                    existing = existing_posts.get(bvid)
                    if existing is not None and _metadata_is_fresh(existing, item, now):
                        if "play" in item:
                            existing.view_count = _parse_view_count(item["play"])
                        session.add(existing)
                        changed += 1
                        continue
                    detail: dict[str, Any] | None = None
                    metadata_error: str | None = None
                    try:
                        detail = await fetch_bilibili_video_detail(bvid)
                    except Exception as exc:
                        metadata_error = str(exc)[:500]

                    source = detail if detail is not None else item
                    if detail is None and existing is not None:
                        source = {
                            "title": existing.title,
                            "description": existing.description,
                            "duration": existing.duration_seconds,
                            "play": existing.view_count,
                            **item,
                        }
                        # Preserve canonical text when the listing is only a prefix,
                        # but allow an edited listing description to qualify a video.
                        listed_description = item.get("description")
                        if not isinstance(listed_description, str) or (
                            existing.description or ""
                        ).startswith(listed_description):
                            source["description"] = existing.description
                    title = str(source.get("title") or "Untitled video")[:500]
                    description = (
                        str(source.get("desc") or source.get("description") or "")[
                            :10000
                        ]
                        or None
                    )
                    tags: list[str] | None = None
                    classification = classify_media_post(
                        title=title, description=description, tags=None
                    )
                    metadata_resolved = detail is not None
                    if metadata_resolved and not classification.is_kz_video:
                        try:
                            tags = await fetch_bilibili_video_tags(bvid)
                            classification = classify_media_post(
                                title=title, description=description, tags=tags
                            )
                        except Exception as exc:
                            metadata_resolved = False
                            metadata_error = str(exc)[:500]

                    # Positive text matches in the upload listing remain valid even
                    # when canonical enrichment is temporarily blocked.
                    is_kz_video = classification.is_kz_video
                    if (
                        not metadata_resolved
                        and existing is not None
                        and existing.is_kz_video
                    ):
                        is_kz_video = True
                    stored_tags = (
                        tags
                        if tags is not None
                        else (existing.tags if existing else None)
                    )
                    thumbnail_url = (
                        existing.thumbnail_url if existing is not None else None
                    )
                    if is_kz_video and thumbnail_url is None:
                        thumbnail_url = await cache_bilibili_thumbnail(
                            bvid=bvid, raw_url=source.get("pic")
                        )
                    statistics = source.get("stat")
                    values = {
                        "player_social_link_id": link.id,
                        "player_steamid64": link.player_steamid64,
                        "platform": PlayerSocialPlatform.BILIBILI,
                        "external_video_id": bvid,
                        "title": title,
                        "description": description,
                        "tags": stored_tags,
                        "is_kz_video": is_kz_video,
                        "url": f"https://www.bilibili.com/video/{bvid}",
                        "thumbnail_url": thumbnail_url,
                        "published_at": published_at,
                        "view_count": _parse_view_count(
                            statistics.get("view")
                            if isinstance(statistics, dict)
                            else source.get("play")
                        ),
                        "discovered_at": now,
                        "duration_seconds": _parse_duration(
                            source.get("duration") or source.get("length")
                        ),
                        "available": True,
                        "last_checked_at": now,
                        "metadata_checked_at": now if metadata_resolved else None,
                        "last_error": metadata_error,
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
                                    "tags",
                                    "is_kz_video",
                                    "url",
                                    "thumbnail_url",
                                    "published_at",
                                    "view_count",
                                    "duration_seconds",
                                    "available",
                                    "last_checked_at",
                                    "metadata_checked_at",
                                    "last_error",
                                )
                            },
                        )
                    )
                    await session.exec(statement)
                    changed += 1
            except BilibiliBackoffError:
                # Upload/key endpoints are shared by all creators. The first
                # rejection pauses this poll; already-processed posts still commit.
                break
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
