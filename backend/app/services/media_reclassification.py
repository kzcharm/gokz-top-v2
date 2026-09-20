from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import MediaPost, PlayerSocialPlatform, get_datetime_utc
from app.services.bilibili_media import (
    cache_bilibili_thumbnail,
    fetch_bilibili_video_detail,
    fetch_bilibili_video_tags,
)
from app.services.media_classifier import MediaMatchReason, classify_media_post
from app.services.youtube_media import (
    _thumbnail_url,
    cache_youtube_thumbnail,
    fetch_youtube_video_metadata,
)

MEDIA_RETENTION_DAYS = 90


@dataclass
class MediaReclassificationResult:
    inspected: int = 0
    matched_by_reason: Counter[MediaMatchReason] = field(default_factory=Counter)
    rejected: int = 0
    unchanged: int = 0
    failed: int = 0
    dry_run: bool = False


def _changed(
    post: MediaPost,
    *,
    title: str,
    description: str | None,
    tags: list[str] | None,
    is_kz_video: bool,
) -> bool:
    return (
        post.title != title
        or post.description != description
        or post.tags != tags
        or post.is_kz_video != is_kz_video
    )


async def reclassify_media_posts(
    *,
    session: AsyncSession,
    platform: PlayerSocialPlatform | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> MediaReclassificationResult:
    result = MediaReclassificationResult(dry_run=dry_run)
    statement = (
        select(MediaPost)
        .where(
            col(MediaPost.platform).in_(
                [PlayerSocialPlatform.YOUTUBE, PlayerSocialPlatform.BILIBILI]
            ),
            col(MediaPost.published_at)
            >= get_datetime_utc() - timedelta(days=MEDIA_RETENTION_DAYS),
        )
        .order_by(col(MediaPost.published_at).desc(), col(MediaPost.id).desc())
    )
    if platform is not None:
        statement = statement.where(col(MediaPost.platform) == platform)
    if limit is not None:
        statement = statement.limit(limit)
    posts = list((await session.exec(statement)).all())

    youtube_posts = [
        post for post in posts if post.platform == PlayerSocialPlatform.YOUTUBE
    ]
    for start in range(0, len(youtube_posts), 50):
        batch = youtube_posts[start : start + 50]
        try:
            metadata = await fetch_youtube_video_metadata(
                [post.external_video_id for post in batch]
            )
        except Exception:
            result.inspected += len(batch)
            result.failed += len(batch)
            continue
        for post in batch:
            result.inspected += 1
            video = metadata.get(post.external_video_id)
            snippet = video.get("snippet") if video is not None else None
            if not isinstance(snippet, dict):
                result.failed += 1
                continue
            title = str(snippet.get("title") or "Untitled video")[:500]
            description = str(snippet.get("description") or "")[:10000] or None
            raw_tags = snippet.get("tags")
            tags = (
                [tag for tag in raw_tags if isinstance(tag, str)]
                if isinstance(raw_tags, list)
                else []
            )
            classification = classify_media_post(
                title=title, description=description, tags=tags
            )
            if classification.is_kz_video:
                result.matched_by_reason[classification.reason] += 1
            else:
                result.rejected += 1
            changed = _changed(
                post,
                title=title,
                description=description,
                tags=tags,
                is_kz_video=classification.is_kz_video,
            )
            if not changed:
                result.unchanged += 1
            if dry_run:
                continue
            if classification.is_kz_video and not post.is_kz_video:
                post.thumbnail_url = await cache_youtube_thumbnail(
                    video_id=post.external_video_id,
                    raw_url=_thumbnail_url(snippet),
                )
            post.title = title
            post.description = description
            post.tags = tags
            post.is_kz_video = classification.is_kz_video
            post.last_error = None

    bilibili_posts = [
        post for post in posts if post.platform == PlayerSocialPlatform.BILIBILI
    ]
    for post in bilibili_posts:
        result.inspected += 1
        try:
            detail = await fetch_bilibili_video_detail(post.external_video_id)
            title = str(detail.get("title") or "Untitled video")[:500]
            description = str(detail.get("desc") or "")[:10000] or None
            classification = classify_media_post(
                title=title, description=description, tags=None
            )
            bilibili_tags = post.tags
            if not classification.is_kz_video:
                bilibili_tags = await fetch_bilibili_video_tags(post.external_video_id)
                classification = classify_media_post(
                    title=title, description=description, tags=bilibili_tags
                )
        except Exception:
            result.failed += 1
            continue
        if classification.is_kz_video:
            result.matched_by_reason[classification.reason] += 1
        else:
            result.rejected += 1
        changed = _changed(
            post,
            title=title,
            description=description,
            tags=bilibili_tags,
            is_kz_video=classification.is_kz_video,
        )
        if not changed:
            result.unchanged += 1
        if dry_run:
            continue
        if classification.is_kz_video and not post.is_kz_video:
            post.thumbnail_url = await cache_bilibili_thumbnail(
                bvid=post.external_video_id, raw_url=detail.get("pic")
            )
        post.title = title
        post.description = description
        post.tags = bilibili_tags
        post.is_kz_video = classification.is_kz_video
        post.last_error = None

    if not dry_run:
        await session.commit()
    return result


__all__ = ["MediaReclassificationResult", "reclassify_media_posts"]
