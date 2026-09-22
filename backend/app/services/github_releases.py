import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.crud.content_reaction import load_reaction_summaries
from app.models import (
    GitHubRelease,
    GitHubReleasePublic,
    GitHubReleasesPublic,
    ReactionSummaryPublic,
    ReactionTargetType,
)

logger = logging.getLogger(__name__)

GITHUB_RELEASES_URL = "https://api.github.com/repos/kzcharm/gokz-top-v2/releases"
GITHUB_RELEASE_CACHE_SIZE = 20


class GitHubReleasesUnavailableError(RuntimeError):
    pass


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


async def fetch_github_releases(*, limit: int) -> list[dict[str, Any]]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "gokz-top-v2",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
        response = await client.get(GITHUB_RELEASES_URL, params={"per_page": limit})
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("GitHub returned an invalid releases response")
    return [item for item in payload if isinstance(item, dict)]


async def _cached_releases(*, session: AsyncSession, limit: int) -> list[GitHubRelease]:
    return list(
        (
            await session.exec(
                select(GitHubRelease)
                .where(col(GitHubRelease.is_listed).is_(True))
                .order_by(
                    col(GitHubRelease.published_at).desc().nulls_last(),
                    col(GitHubRelease.id).desc(),
                )
                .limit(limit)
            )
        ).all()
    )


async def refresh_github_release_cache(*, session: AsyncSession) -> list[GitHubRelease]:
    cached = await _cached_releases(session=session, limit=GITHUB_RELEASE_CACHE_SIZE)
    now = datetime.now(UTC)
    if cached and max(release.synced_at for release in cached) > now - timedelta(
        seconds=settings.GITHUB_RELEASES_CACHE_TTL_SECONDS
    ):
        return cached
    try:
        payload = await fetch_github_releases(limit=GITHUB_RELEASE_CACHE_SIZE)
    except (httpx.HTTPError, ValueError) as exc:
        if cached:
            logger.warning(
                "Serving stale GitHub releases after refresh failure: %s", exc
            )
            return cached
        raise GitHubReleasesUnavailableError(
            "GitHub releases are temporarily unavailable"
        ) from exc

    await session.exec(update(GitHubRelease).values(is_listed=False))
    for item in payload:
        release_id = item.get("id")
        tag_name = item.get("tag_name")
        html_url = item.get("html_url")
        if (
            not isinstance(release_id, int)
            or not isinstance(tag_name, str)
            or not isinstance(html_url, str)
        ):
            continue
        release_name = item.get("name")
        values = {
            "id": release_id,
            "tag_name": tag_name[:255],
            "name": release_name[:255] if isinstance(release_name, str) else None,
            "html_url": html_url[:1000],
            "published_at": _parse_datetime(item.get("published_at")),
            "body": item.get("body") if isinstance(item.get("body"), str) else None,
            "is_listed": True,
            "synced_at": now,
        }
        statement = insert(GitHubRelease).values(**values)
        await session.exec(
            statement.on_conflict_do_update(
                index_elements=["id"],
                set_={key: value for key, value in values.items() if key != "id"},
            )
        )
    await session.commit()
    return await _cached_releases(session=session, limit=GITHUB_RELEASE_CACHE_SIZE)


async def read_github_releases(
    *, session: AsyncSession, limit: int, viewer_steamid64: int | None
) -> GitHubReleasesPublic:
    releases = (await refresh_github_release_cache(session=session))[:limit]
    summaries = await load_reaction_summaries(
        session=session,
        target_type=ReactionTargetType.RELEASE,
        target_ids=[release.id for release in releases],
        viewer_steamid64=viewer_steamid64,
    )
    return GitHubReleasesPublic(
        data=[
            GitHubReleasePublic(
                id=release.id,
                tag_name=release.tag_name,
                name=release.name,
                html_url=release.html_url,
                published_at=release.published_at,
                body=release.body,
                reactions=summaries.get(release.id, ReactionSummaryPublic()),
            )
            for release in releases
        ]
    )
