from __future__ import annotations

import base64
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from urllib.parse import urlencode

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import (
    MediaPost,
    MediaPostPlayerPublic,
    MediaPostPublic,
    MediaPostsPublic,
    MediaPostViewCountPublic,
    MediaPostViewCountsRefreshPublic,
    Player,
    PlayerSocialPlatform,
)

logger = logging.getLogger(__name__)


def resolve_media_thumbnail_url(post: MediaPost) -> str | None:
    if post.thumbnail_url is None:
        return None
    if post.platform == PlayerSocialPlatform.BILIBILI:
        from app.services.bilibili_media import is_allowed_bilibili_thumbnail_url

        if not is_allowed_bilibili_thumbnail_url(post.thumbnail_url):
            return post.thumbnail_url
        return (
            f"{settings.BACKEND_PUBLIC_URL.rstrip('/')}{settings.API_V1_STR}"
            f"/media/thumbnail?{urlencode({'url': post.thumbnail_url})}"
        )
    return post.thumbnail_url


async def fetch_youtube_video_view_counts(
    video_ids: list[str],
) -> dict[str, int]:
    from app.services.youtube_media import fetch_youtube_video_view_counts as fetch

    return cast(dict[str, int], await fetch(video_ids))


async def fetch_bilibili_video_view_counts(
    video_ids: list[str],
) -> dict[str, int]:
    from app.services.bilibili_media import fetch_bilibili_video_view_counts as fetch

    return await fetch(video_ids)


def encode_media_cursor(post: MediaPost) -> str:
    raw = f"{post.published_at.isoformat()}|{post.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    padded = cursor + "=" * (-len(cursor) % 4)
    published, post_id = (
        base64.urlsafe_b64decode(padded.encode()).decode().split("|", 1)
    )
    parsed = datetime.fromisoformat(published)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed, uuid.UUID(post_id)


async def read_media_posts(
    *,
    session: AsyncSession,
    cursor: str | None,
    limit: int,
    steamid64: str | None,
    from_: datetime | None,
    to: datetime | None,
) -> MediaPostsPublic:
    filters: list[Any] = [
        col(MediaPost.platform).in_(
            [PlayerSocialPlatform.YOUTUBE, PlayerSocialPlatform.BILIBILI]
        )
    ]
    if steamid64 is not None:
        filters.append(col(MediaPost.player_steamid64) == int(steamid64))
    if from_ is not None:
        filters.append(col(MediaPost.published_at) >= from_)
    if to is not None:
        filters.append(col(MediaPost.published_at) <= to)
    if cursor:
        published_at, post_id = _decode_cursor(cursor)
        filters.append(
            (col(MediaPost.published_at) < published_at)
            | (
                (col(MediaPost.published_at) == published_at)
                & (col(MediaPost.id) < post_id)
            )
        )
    statement = (
        select(MediaPost, Player)
        .join(Player, col(Player.steamid64) == col(MediaPost.player_steamid64))
        .where(*filters)
        .order_by(col(MediaPost.published_at).desc(), col(MediaPost.id).desc())
        .limit(limit + 1)
    )
    rows = list((await session.exec(statement)).all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    data = [
        MediaPostPublic(
            id=post.id,
            player=MediaPostPlayerPublic(
                steamid64=str(player.steamid64),
                display_name=player.alias or player.name,
            ),
            platform=post.platform,
            external_video_id=post.external_video_id,
            title=post.title,
            description=post.description,
            url=post.url,
            thumbnail_url=resolve_media_thumbnail_url(post),
            published_at=post.published_at,
            view_count=post.view_count,
            duration_seconds=post.duration_seconds,
            available=post.available,
        )
        for post, player in rows
    ]
    return MediaPostsPublic(
        data=data,
        next_cursor=encode_media_cursor(rows[-1][0]) if has_more and rows else None,
        count=len(data),
    )


async def prune_media_posts(*, session: AsyncSession, before: datetime) -> int:
    from sqlalchemy import delete

    result = await session.exec(
        delete(MediaPost).where(col(MediaPost.published_at) < before)
    )
    await session.commit()
    return int(result.rowcount or 0)


async def refresh_media_post_view_counts(
    *, session: AsyncSession, post_ids: list[uuid.UUID]
) -> MediaPostViewCountsRefreshPublic:
    unique_post_ids = list(dict.fromkeys(post_ids))
    if not unique_post_ids:
        return MediaPostViewCountsRefreshPublic(data=[])

    now = datetime.now(UTC)
    stale_before = now - timedelta(
        seconds=settings.MEDIA_VIEW_COUNT_REFRESH_TTL_SECONDS
    )
    posts = list(
        (
            await session.exec(
                select(MediaPost).where(
                    col(MediaPost.id).in_(unique_post_ids),
                    col(MediaPost.platform).in_(
                        [PlayerSocialPlatform.YOUTUBE, PlayerSocialPlatform.BILIBILI]
                    ),
                    col(MediaPost.last_checked_at) < stale_before,
                )
            )
        ).all()
    )
    if not posts:
        return MediaPostViewCountsRefreshPublic(data=[])

    refreshed: list[MediaPostViewCountPublic] = []
    for platform, fetch_view_counts in (
        (PlayerSocialPlatform.YOUTUBE, fetch_youtube_video_view_counts),
        (PlayerSocialPlatform.BILIBILI, fetch_bilibili_video_view_counts),
    ):
        platform_posts = [post for post in posts if post.platform == platform]
        if not platform_posts:
            continue
        try:
            view_counts = await fetch_view_counts(
                [post.external_video_id for post in platform_posts]
            )
        except Exception as exc:
            logger.warning("Media view-count refresh failed", exc_info=True)
            error = str(exc)[:500]
            for post in platform_posts:
                post.last_error = error
            continue
        for post in platform_posts:
            view_count = view_counts.get(post.external_video_id)
            if view_count is None:
                continue
            post.view_count = view_count
            post.last_checked_at = now
            post.last_error = None
            refreshed.append(
                MediaPostViewCountPublic(id=post.id, view_count=view_count)
            )
    if refreshed or posts:
        await session.commit()
    return MediaPostViewCountsRefreshPublic(data=refreshed)


__all__ = [
    "encode_media_cursor",
    "prune_media_posts",
    "read_media_posts",
    "refresh_media_post_view_counts",
]
