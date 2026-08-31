from __future__ import annotations

import asyncio
import hashlib
import logging
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
from app.models import (
    LiveStreamState,
    Player,
    PlayerSocialLink,
    PlayerSocialPlatform,
    generate_uuid7,
    get_datetime_utc,
)
from app.services import r2_storage
from app.services.player_social_links import build_player_social_link_url
from app.services.player_webhooks import (
    DiscordWebhookStreamEvent,
    build_discord_embed_payload,
    build_player_profile_url,
    send_discord_webhook,
)

logger = logging.getLogger(__name__)

ENABLED_LIVE_STREAM_PLATFORMS: tuple[PlayerSocialPlatform, ...] = (
    PlayerSocialPlatform.BILIBILI,
    PlayerSocialPlatform.TWITCH,
)
BILIBILI_PREVIEW_HOST_SUFFIXES = ("hdslb.com",)
TWITCH_STREAMS_CHUNK_SIZE = 100
TWITCH_THUMBNAIL_WIDTH = 640
TWITCH_THUMBNAIL_HEIGHT = 360
TWITCH_TOKEN_REFRESH_BUFFER = timedelta(seconds=60)
LIVE_STREAM_KEYFRAME_R2_PREFIX = "live/keyframes"
LIVE_STREAM_KEYFRAME_CACHE_CONTROL = "public, max-age=31536000, immutable"
LIVE_STREAM_KEYFRAME_CLEANUP_INTERVAL = timedelta(hours=1)
LIVE_STREAM_KEYFRAME_ORPHAN_GRACE = timedelta(hours=24)
LIVE_STREAM_RUNNER_LOCK_ID = int.from_bytes(
    hashlib.sha256(b"gokz-top-v2:live-stream-runner").digest()[:8],
    byteorder="big",
    signed=True,
)


@dataclass(frozen=True, slots=True)
class LiveStreamStatus:
    is_live: bool
    stream_title: str | None = None
    viewer_count: int | None = None
    preview_image_url: str | None = None
    hover_preview_image_url: str | None = None
    stream_url: str | None = None
    channel_display_name: str | None = None
    started_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class TwitchAppAccessToken:
    access_token: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class LiveStreamKeyframeUpdate:
    image_url: str
    r2_key: str | None
    image_sha256: str | None


@dataclass(frozen=True, slots=True)
class LiveStreamKeyframeCleanupResult:
    checked: int
    deleted: int
    errors: int


BilibiliLiveStatus = LiveStreamStatus
TwitchLiveStatus = LiveStreamStatus
_twitch_app_access_token: TwitchAppAccessToken | None = None


def get_live_stream_stale_after() -> timedelta:
    return timedelta(seconds=max(settings.LIVE_STREAM_POLL_SECONDS * 3, 60))


def build_live_preview_proxy_url(raw_url: str) -> str:
    encoded_url = urlencode({"url": raw_url})
    return f"{settings.API_V1_STR}/live/preview-image?{encoded_url}"


def resolve_live_preview_url(raw_url: str) -> str:
    return (
        build_live_preview_proxy_url(raw_url)
        if is_allowed_live_preview_url(raw_url)
        else raw_url
    )


def is_allowed_live_preview_url(url: str) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme != "https":
        return False
    host = parsed.netloc.split(":", maxsplit=1)[0].lower()
    return any(
        host == suffix or host.endswith(f".{suffix}")
        for suffix in BILIBILI_PREVIEW_HOST_SUFFIXES
    )


async def fetch_live_preview_image(url: str) -> tuple[bytes, str]:
    if not is_allowed_live_preview_url(url):
        raise ValueError("Preview URL host is not allowed")

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        media_type = response.headers.get("content-type", "image/jpeg")
        return response.content, media_type


def _build_live_stream_keyframe_object_key(
    *,
    platform: PlayerSocialPlatform,
    social_link_id: object,
) -> str:
    return (
        f"{LIVE_STREAM_KEYFRAME_R2_PREFIX}/{platform.value}/{social_link_id}/"
        f"{generate_uuid7()}.jpg"
    )


def _is_allowed_stream_keyframe_source_url(url: str) -> bool:
    parsed = urlsplit(url)
    return parsed.scheme == "https" and bool(parsed.netloc)


async def _fetch_stream_keyframe_image(url: str) -> tuple[bytes, str]:
    if not _is_allowed_stream_keyframe_source_url(url):
        raise ValueError("Stream keyframe source URL is not allowed")

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()

    if response.url.scheme != "https":
        raise ValueError("Stream keyframe source redirected to a non-HTTPS URL")

    media_type = (
        response.headers.get("content-type", "image/jpeg")
        .split(
            ";",
            maxsplit=1,
        )[0]
        .strip()
    )
    if not media_type.startswith("image/"):
        raise ValueError("Stream keyframe source did not return an image")
    return response.content, media_type


async def _save_live_stream_keyframe_image(
    *,
    link: PlayerSocialLink,
    status: LiveStreamStatus,
    previous_state: LiveStreamState | None,
) -> LiveStreamKeyframeUpdate | None:
    source_url = status.hover_preview_image_url or status.preview_image_url
    if not status.is_live or not source_url:
        return None
    if not r2_storage.is_configured():
        return LiveStreamKeyframeUpdate(source_url, None, None)

    try:
        content, media_type = await _fetch_stream_keyframe_image(source_url)
        image_sha256 = hashlib.sha256(content).hexdigest()
        if (
            previous_state is not None
            and previous_state.last_keyframe_r2_key is not None
            and previous_state.last_keyframe_image_sha256 == image_sha256
        ):
            return LiveStreamKeyframeUpdate(
                image_url=(
                    previous_state.last_keyframe_image_url
                    or r2_storage.build_public_url(previous_state.last_keyframe_r2_key)
                ),
                r2_key=previous_state.last_keyframe_r2_key,
                image_sha256=image_sha256,
            )

        r2_key = _build_live_stream_keyframe_object_key(
            platform=link.platform,
            social_link_id=link.id,
        )
        image_url = await r2_storage.put_object(
            key=r2_key,
            body=content,
            content_type=media_type,
            cache_control=LIVE_STREAM_KEYFRAME_CACHE_CONTROL,
        )
        return LiveStreamKeyframeUpdate(image_url, r2_key, image_sha256)
    except Exception:
        logger.exception(
            "Failed to save live stream keyframe to R2",
            extra={
                "platform": link.platform.value,
                "social_link_id": str(link.id),
            },
        )
        return LiveStreamKeyframeUpdate(source_url, None, None)


def _is_managed_keyframe_key(key: str) -> bool:
    return key.startswith(f"{LIVE_STREAM_KEYFRAME_R2_PREFIX}/")


def _state_keyframe_r2_key(state: LiveStreamState | None) -> str | None:
    if state is None:
        return None
    if state.last_keyframe_r2_key is not None:
        return state.last_keyframe_r2_key
    if state.last_keyframe_image_url is None:
        return None
    return r2_storage.public_url_to_key(state.last_keyframe_image_url)


async def _delete_superseded_keyframes(keys: set[str]) -> None:
    for key in sorted(keys):
        if not _is_managed_keyframe_key(key):
            continue
        try:
            await r2_storage.delete_object(key=key)
        except Exception:
            logger.exception(
                "Failed to delete superseded live stream keyframe from R2",
                extra={"r2_key": key},
            )


async def cleanup_orphaned_live_stream_keyframes_once(
    *,
    session: AsyncSession | None = None,
    now: datetime | None = None,
) -> LiveStreamKeyframeCleanupResult:
    if not r2_storage.is_configured():
        return LiveStreamKeyframeCleanupResult(checked=0, deleted=0, errors=0)

    if session is None:
        async with async_session_maker() as managed_session:
            return await cleanup_orphaned_live_stream_keyframes_once(
                session=managed_session,
                now=now,
            )

    references = await crud.list_live_stream_keyframe_storage_references(
        session=session
    )
    referenced_keys: set[str] = set()
    for key, image_url in references:
        resolved_key = key or (
            r2_storage.public_url_to_key(image_url) if image_url else None
        )
        if resolved_key is not None:
            referenced_keys.add(resolved_key)
    objects = await r2_storage.list_objects(prefix=f"{LIVE_STREAM_KEYFRAME_R2_PREFIX}/")
    cutoff = (now or get_datetime_utc()) - LIVE_STREAM_KEYFRAME_ORPHAN_GRACE
    deleted = 0
    errors = 0
    for object_info in objects:
        if (
            not _is_managed_keyframe_key(object_info.key)
            or object_info.key in referenced_keys
            or object_info.last_modified >= cutoff
        ):
            continue
        try:
            await r2_storage.delete_object(key=object_info.key)
            deleted += 1
        except Exception:
            errors += 1
            logger.exception(
                "Failed to delete orphaned live stream keyframe from R2",
                extra={"r2_key": object_info.key},
            )
    return LiveStreamKeyframeCleanupResult(
        checked=len(objects),
        deleted=deleted,
        errors=errors,
    )


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
        return datetime.strptime(normalized, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def _parse_non_negative_int(value: object | None) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str):
        normalized = value.strip()
        if normalized.isdecimal():
            parsed = int(normalized)
            return parsed if parsed >= 0 else None
    return None


async def check_bilibili_live_status(
    uids: Sequence[int],
) -> dict[int, BilibiliLiveStatus]:
    if not uids:
        return {}

    result = {uid: BilibiliLiveStatus(is_live=False) for uid in uids}
    response_data = await _fetch_bilibili_live_status_payload(list(uids))
    live_infos: list[tuple[int, dict[str, Any], int | None]] = []
    viewer_count_tasks: dict[int, asyncio.Task[int | None]] = {}
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

        room_id = _parse_non_negative_int(info.get("room_id"))
        if room_id is not None:
            viewer_count_tasks[uid] = asyncio.create_task(
                _fetch_bilibili_room_viewer_count(
                    room_id=room_id,
                    ruid=uid,
                )
            )
        live_infos.append((uid, info, room_id))

    for uid, info, room_id in live_infos:
        viewer_count = None
        viewer_count_task = viewer_count_tasks.get(uid)
        if viewer_count_task is not None:
            try:
                viewer_count = await viewer_count_task
            except Exception:
                logger.exception(
                    "Failed to refresh Bilibili room viewer count",
                    extra={"room_id": room_id, "ruid": uid},
                )
        stream_url = f"https://live.bilibili.com/{room_id}" if room_id else None
        result[uid] = BilibiliLiveStatus(
            is_live=True,
            stream_title=info.get("title"),
            viewer_count=viewer_count,
            preview_image_url=info.get("cover_from_user") or info.get("keyframe"),
            hover_preview_image_url=info.get("keyframe") or None,
            stream_url=stream_url,
            channel_display_name=info.get("uname"),
            started_at=_parse_bilibili_started_at(info.get("live_time")),
        )
    return result


def is_twitch_live_stream_polling_enabled() -> bool:
    return bool(settings.TWITCH_CLIENT_ID and settings.TWITCH_CLIENT_SECRET)


def _clear_twitch_app_access_token_cache() -> None:
    global _twitch_app_access_token
    _twitch_app_access_token = None


def _parse_twitch_started_at(value: object | None) -> datetime | None:
    if not isinstance(value, str):
        return None

    normalized = value.strip()
    if not normalized:
        return None

    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _expand_twitch_thumbnail_url(template: object | None) -> str | None:
    if not isinstance(template, str):
        return None
    normalized = template.strip()
    if not normalized:
        return None
    return normalized.replace("{width}", str(TWITCH_THUMBNAIL_WIDTH)).replace(
        "{height}", str(TWITCH_THUMBNAIL_HEIGHT)
    )


async def _fetch_twitch_app_access_token() -> TwitchAppAccessToken:
    if not is_twitch_live_stream_polling_enabled():
        raise RuntimeError("Twitch live polling credentials are not configured")

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            "https://id.twitch.tv/oauth2/token",
            data={
                "client_id": settings.TWITCH_CLIENT_ID,
                "client_secret": settings.TWITCH_CLIENT_SECRET,
                "grant_type": "client_credentials",
            },
        )
        response.raise_for_status()
        payload = response.json()

    access_token = payload.get("access_token")
    expires_in = payload.get("expires_in")
    if not isinstance(access_token, str) or not access_token.strip():
        raise ValueError("Twitch OAuth response did not include an access token")
    if not isinstance(expires_in, int | float) or expires_in <= 0:
        raise ValueError("Twitch OAuth response did not include a valid expiry")

    return TwitchAppAccessToken(
        access_token=access_token,
        expires_at=get_datetime_utc() + timedelta(seconds=int(expires_in)),
    )


async def _get_twitch_app_access_token(*, force_refresh: bool = False) -> str:
    global _twitch_app_access_token

    now = get_datetime_utc()
    if (
        force_refresh is False
        and _twitch_app_access_token is not None
        and _twitch_app_access_token.expires_at - TWITCH_TOKEN_REFRESH_BUFFER > now
    ):
        return _twitch_app_access_token.access_token

    _twitch_app_access_token = await _fetch_twitch_app_access_token()
    return _twitch_app_access_token.access_token


async def _fetch_twitch_streams_payload(
    user_logins: list[str],
    *,
    access_token: str,
) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://api.twitch.tv/helix/streams",
            params=[("user_login", user_login) for user_login in user_logins],
            headers={
                "Authorization": f"Bearer {access_token}",
                "Client-Id": settings.TWITCH_CLIENT_ID or "",
            },
        )
        response.raise_for_status()
        payload = response.json()

    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError("Twitch streams API returned an invalid payload")
    return [item for item in data if isinstance(item, dict)]


async def check_twitch_live_status(
    account_identifiers: Sequence[str],
) -> dict[str, TwitchLiveStatus]:
    if not account_identifiers:
        return {}
    if not is_twitch_live_stream_polling_enabled():
        raise RuntimeError("Twitch live polling credentials are not configured")

    normalized_identifiers = list(dict.fromkeys(account_identifiers))
    result = {
        account_identifier: TwitchLiveStatus(is_live=False)
        for account_identifier in normalized_identifiers
    }

    access_token = await _get_twitch_app_access_token()
    payloads: list[dict[str, Any]] = []
    for attempt in range(2):
        try:
            payloads.clear()
            for index in range(
                0, len(normalized_identifiers), TWITCH_STREAMS_CHUNK_SIZE
            ):
                chunk = normalized_identifiers[
                    index : index + TWITCH_STREAMS_CHUNK_SIZE
                ]
                payloads.extend(
                    await _fetch_twitch_streams_payload(
                        chunk,
                        access_token=access_token,
                    )
                )
            break
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 401 or attempt == 1:
                raise
            access_token = await _get_twitch_app_access_token(force_refresh=True)

    for stream in payloads:
        user_login = stream.get("user_login")
        if not isinstance(user_login, str) or user_login not in result:
            continue

        result[user_login] = TwitchLiveStatus(
            is_live=True,
            stream_title=stream.get("title")
            if isinstance(stream.get("title"), str)
            else None,
            viewer_count=stream.get("viewer_count")
            if isinstance(stream.get("viewer_count"), int)
            else None,
            preview_image_url=_expand_twitch_thumbnail_url(stream.get("thumbnail_url")),
            hover_preview_image_url=None,
            stream_url=f"https://www.twitch.tv/{user_login}",
            channel_display_name=stream.get("user_name")
            if isinstance(stream.get("user_name"), str)
            else None,
            started_at=_parse_twitch_started_at(stream.get("started_at")),
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


async def _fetch_bilibili_room_viewer_count(*, room_id: int, ruid: int) -> int | None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://api.live.bilibili.com/xlive/general-interface/v1/rank/getOnlineGoldRank",
            params={
                "roomId": room_id,
                "ruid": ruid,
                "page": 1,
                "pageSize": 1,
            },
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/91.0.4472.124 Safari/537.36"
                ),
            },
        )
        response.raise_for_status()
        payload = response.json()

    if payload.get("code") != 0:
        raise ValueError(payload.get("message") or "Bilibili viewer API error")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("Bilibili viewer API returned an invalid payload")
    return _parse_non_negative_int(data.get("onlineNum"))


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

    processed = 0
    superseded_keyframe_keys: set[str] = set()
    bilibili_links = [
        link for link in links if link.platform == PlayerSocialPlatform.BILIBILI
    ]
    if bilibili_links:
        try:
            bilibili_statuses = await check_bilibili_live_status(
                [int(link.account_identifier) for link in bilibili_links]
            )
        except Exception:
            logger.exception("Failed to refresh Bilibili live streams")
        else:
            checked_at = get_datetime_utc()
            for link in bilibili_links:
                previous_state = await crud.get_live_stream_state(
                    session=session,
                    social_link_id=link.id,
                )
                previous_is_live = (
                    previous_state.is_live if previous_state is not None else None
                )
                previous_live_started_at = (
                    previous_state.last_live_started_at
                    if previous_state is not None
                    else None
                )
                previous_keyframe_r2_key = _state_keyframe_r2_key(previous_state)
                status = bilibili_statuses.get(
                    int(link.account_identifier),
                    BilibiliLiveStatus(False),
                )
                keyframe_update = await _save_live_stream_keyframe_image(
                    link=link,
                    status=status,
                    previous_state=previous_state,
                )
                state = await crud.upsert_live_stream_state(
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
                    hover_preview_image_url=(
                        keyframe_update.image_url if keyframe_update else None
                    ),
                    keyframe_r2_key=(
                        keyframe_update.r2_key if keyframe_update else None
                    ),
                    keyframe_image_sha256=(
                        keyframe_update.image_sha256 if keyframe_update else None
                    ),
                    update_keyframe=keyframe_update is not None,
                    channel_display_name=status.channel_display_name,
                    viewer_count=status.viewer_count,
                    update_viewer_count=status.is_live,
                    started_at=status.started_at,
                    commit=False,
                )
                await _notify_stream_started_if_needed(
                    session=session,
                    player_steamid64=link.player_steamid64,
                    link=link,
                    previous_is_live=previous_is_live,
                    previous_live_started_at=previous_live_started_at,
                    current_state=state,
                )
                if (
                    keyframe_update is not None
                    and previous_keyframe_r2_key is not None
                    and previous_keyframe_r2_key != keyframe_update.r2_key
                ):
                    superseded_keyframe_keys.add(previous_keyframe_r2_key)
            processed += len(bilibili_links)

    twitch_links = [
        link for link in links if link.platform == PlayerSocialPlatform.TWITCH
    ]
    if twitch_links and not is_twitch_live_stream_polling_enabled():
        logger.info(
            "Skipping Twitch live stream refresh because credentials are not configured"
        )
    elif twitch_links:
        try:
            twitch_statuses = await check_twitch_live_status(
                [link.account_identifier for link in twitch_links]
            )
        except Exception:
            logger.exception("Failed to refresh Twitch live streams")
        else:
            checked_at = get_datetime_utc()
            for link in twitch_links:
                previous_state = await crud.get_live_stream_state(
                    session=session,
                    social_link_id=link.id,
                )
                previous_is_live = (
                    previous_state.is_live if previous_state is not None else None
                )
                previous_live_started_at = (
                    previous_state.last_live_started_at
                    if previous_state is not None
                    else None
                )
                previous_keyframe_r2_key = _state_keyframe_r2_key(previous_state)
                status = twitch_statuses.get(
                    link.account_identifier,
                    TwitchLiveStatus(False),
                )
                keyframe_update = await _save_live_stream_keyframe_image(
                    link=link,
                    status=status,
                    previous_state=previous_state,
                )
                state = await crud.upsert_live_stream_state(
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
                    hover_preview_image_url=(
                        keyframe_update.image_url if keyframe_update else None
                    ),
                    keyframe_r2_key=(
                        keyframe_update.r2_key if keyframe_update else None
                    ),
                    keyframe_image_sha256=(
                        keyframe_update.image_sha256 if keyframe_update else None
                    ),
                    update_keyframe=keyframe_update is not None,
                    channel_display_name=status.channel_display_name,
                    viewer_count=status.viewer_count,
                    update_viewer_count=status.is_live,
                    started_at=status.started_at,
                    commit=False,
                )
                await _notify_stream_started_if_needed(
                    session=session,
                    player_steamid64=link.player_steamid64,
                    link=link,
                    previous_is_live=previous_is_live,
                    previous_live_started_at=previous_live_started_at,
                    current_state=state,
                )
                if (
                    keyframe_update is not None
                    and previous_keyframe_r2_key is not None
                    and previous_keyframe_r2_key != keyframe_update.r2_key
                ):
                    superseded_keyframe_keys.add(previous_keyframe_r2_key)
            processed += len(twitch_links)

    await session.commit()
    await _delete_superseded_keyframes(superseded_keyframe_keys)
    return processed


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
                    next_cleanup_at: datetime | None = None
                    while True:
                        now = get_datetime_utc()
                        if next_cleanup_at is None or now >= next_cleanup_at:
                            try:
                                await cleanup_orphaned_live_stream_keyframes_once(
                                    now=now
                                )
                            except Exception:
                                logger.exception(
                                    "Failed to clean up orphaned live stream keyframes"
                                )
                            next_cleanup_at = (
                                now + LIVE_STREAM_KEYFRAME_CLEANUP_INTERVAL
                            )
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


def _is_newly_live_transition(
    *,
    previous_is_live: bool | None,
    previous_live_started_at: datetime | None,
    current_state: LiveStreamState,
) -> bool:
    if current_state.is_live is not True:
        return False
    if previous_is_live is None:
        return True
    if previous_is_live is not True:
        return True

    current_started_at = current_state.last_live_started_at
    return (
        previous_live_started_at is not None
        and current_started_at is not None
        and current_started_at > previous_live_started_at
    )


def _to_stream_event(
    *,
    player: Player,
    link: PlayerSocialLink,
    current_state: LiveStreamState,
) -> DiscordWebhookStreamEvent:
    player_identifier = player.custom_id or str(player.steamid64)
    return DiscordWebhookStreamEvent(
        player_display_name=player.alias or player.name,
        player_avatar_hash=player.avatar_hash,
        player_profile_url=build_player_profile_url(
            frontend_host=settings.FRONTEND_HOST,
            player_identifier=player_identifier,
        ),
        platform=link.platform,
        stream_url=current_state.last_stream_url
        or build_player_social_link_url(
            platform=link.platform,
            account_identifier=link.account_identifier,
        ),
        stream_title=current_state.last_stream_title,
        stream_preview_image_url=(
            current_state.last_keyframe_image_url
            or current_state.last_preview_image_url
        ),
        channel_display_name=current_state.last_channel_display_name,
        viewer_count=current_state.last_viewer_count,
        started_at=current_state.last_live_started_at,
    )


async def _notify_stream_started_if_needed(
    *,
    session: AsyncSession,
    player_steamid64: int,
    link: PlayerSocialLink,
    previous_is_live: bool | None,
    previous_live_started_at: datetime | None,
    current_state: LiveStreamState,
) -> None:
    if not link.show_on_site:
        return
    if not _is_newly_live_transition(
        previous_is_live=previous_is_live,
        previous_live_started_at=previous_live_started_at,
        current_state=current_state,
    ):
        return

    player = await crud.get_player_by_steamid64(
        session=session,
        steamid64=player_steamid64,
    )
    if player is None:
        logger.warning(
            "Skipping stream webhook delivery because player %s was not found",
            player_steamid64,
        )
        return

    webhooks = await crud.list_all_enabled_player_webhooks(session=session)
    if not webhooks:
        return

    payload = build_discord_embed_payload(
        event=_to_stream_event(
            player=player,
            link=link,
            current_state=current_state,
        ),
        is_test=False,
    )
    for webhook in webhooks:
        try:
            await send_discord_webhook(webhook_url=webhook.url, payload=payload)
        except httpx.HTTPError:
            logger.exception(
                "Failed to deliver stream-started webhook",
                extra={
                    "webhook_id": str(webhook.id),
                    "player_steamid64": str(player_steamid64),
                    "platform": link.platform.value,
                },
            )
            continue

        await crud.mark_player_webhook_used(
            session=session,
            webhook=webhook,
            used_at=datetime.now(UTC),
        )
