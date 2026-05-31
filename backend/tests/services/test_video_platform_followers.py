from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import (
    Player,
    PlayerSocialLink,
    PlayerSocialPlatform,
    PlayerVideoPlatformFollowerCache,
)
from app.services import video_platform_followers
from tests.utils.utils import random_steamid64


@pytest.mark.asyncio
async def test_refresh_stale_video_platform_followers_preserves_previous_count(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = Player(steamid64=random_steamid64(), name="Cached Streamer")
    db.add(player)
    await db.commit()

    link = PlayerSocialLink(
        player_steamid64=player.steamid64,
        platform=PlayerSocialPlatform.TWITCH,
        account_identifier="streamer",
        verified=True,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)

    fetched_at = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    cache = PlayerVideoPlatformFollowerCache(
        social_link_id=link.id,
        player_steamid64=player.steamid64,
        platform=link.platform,
        account_identifier=link.account_identifier,
        follower_count=777,
        fetched_at=fetched_at,
        last_attempted_at=fetched_at,
    )
    db.add(cache)
    await db.commit()

    async def _failing_fetch(*, link: PlayerSocialLink) -> int:
        _ = link
        raise RuntimeError("upstream unavailable")

    monkeypatch.setattr(
        settings,
        "VIDEO_PLATFORM_FOLLOWER_CACHE_TTL_SECONDS",
        60,
    )
    monkeypatch.setattr(
        video_platform_followers,
        "fetch_video_platform_follower_count",
        _failing_fetch,
    )
    attempted_at = fetched_at + timedelta(minutes=5)

    await video_platform_followers.refresh_stale_video_platform_follower_caches(
        session=db,
        links=[link],
        now=attempted_at,
    )

    refreshed = await db.get(PlayerVideoPlatformFollowerCache, link.id)
    assert refreshed is not None
    await db.refresh(refreshed)
    assert refreshed.follower_count == 777
    assert refreshed.fetched_at == fetched_at
    assert refreshed.last_attempted_at == attempted_at
    assert refreshed.error_message == "upstream unavailable"
