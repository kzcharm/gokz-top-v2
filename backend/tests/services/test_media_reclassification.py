from datetime import UTC, datetime
from typing import Any

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import MediaPost, Player, PlayerSocialLink, PlayerSocialPlatform
from app.services import media_reclassification
from app.services.media_classifier import MediaMatchReason
from tests.utils.utils import random_steamid64


async def _create_link(
    db: AsyncSession, platform: PlayerSocialPlatform
) -> PlayerSocialLink:
    player = Player(steamid64=random_steamid64(), name="Media Operator")
    db.add(player)
    await db.commit()
    link = PlayerSocialLink(
        player_steamid64=player.steamid64,
        platform=platform,
        account_identifier="@operator"
        if platform == PlayerSocialPlatform.YOUTUBE
        else "1",
        verified=True,
    )
    db.add(link)
    await db.commit()
    return link


@pytest.mark.asyncio
async def test_reclassify_youtube_supports_dry_run_and_idempotent_rerun(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    link = await _create_link(db, PlayerSocialPlatform.YOUTUBE)
    hidden = MediaPost(
        player_social_link_id=link.id,
        player_steamid64=link.player_steamid64,
        platform=PlayerSocialPlatform.YOUTUBE,
        external_video_id="hidden",
        title="Old title",
        url="https://youtube.example/hidden",
        published_at=datetime.now(UTC),
        is_kz_video=False,
    )
    visible = MediaPost(
        player_social_link_id=link.id,
        player_steamid64=link.player_steamid64,
        platform=PlayerSocialPlatform.YOUTUBE,
        external_video_id="visible",
        title="Old KZ title",
        url="https://youtube.example/visible",
        published_at=datetime.now(UTC),
        is_kz_video=True,
    )
    db.add(hidden)
    db.add(visible)
    await db.commit()
    metadata_calls: list[list[str]] = []
    thumbnail_calls: list[str] = []

    async def _metadata(video_ids: list[str]) -> dict[str, dict[str, Any]]:
        metadata_calls.append(video_ids)
        return {
            "hidden": {
                "snippet": {
                    "title": "A run",
                    "description": "New map bkz_fresh",
                    "tags": [],
                    "thumbnails": {"high": {"url": "https://example.com/a.jpg"}},
                }
            },
            "visible": {
                "snippet": {
                    "title": "Cooking stream",
                    "description": "No game here",
                    "tags": [],
                }
            },
        }

    async def _cache(*, video_id: str, raw_url: str | None) -> str | None:
        thumbnail_calls.append(video_id)
        return raw_url

    monkeypatch.setattr(
        media_reclassification, "fetch_youtube_video_metadata", _metadata
    )
    monkeypatch.setattr(media_reclassification, "cache_youtube_thumbnail", _cache)

    dry_run = await media_reclassification.reclassify_media_posts(
        session=db,
        platform=PlayerSocialPlatform.YOUTUBE,
        limit=2,
        dry_run=True,
    )
    await db.refresh(hidden)
    await db.refresh(visible)
    assert hidden.is_kz_video is False
    assert visible.is_kz_video is True
    assert thumbnail_calls == []
    assert dry_run.matched_by_reason[MediaMatchReason.DESCRIPTION_MAP] == 1
    assert dry_run.rejected == 1

    first = await media_reclassification.reclassify_media_posts(
        session=db, platform=PlayerSocialPlatform.YOUTUBE
    )
    await db.refresh(hidden)
    await db.refresh(visible)
    assert hidden.is_kz_video is True
    assert hidden.thumbnail_url == "https://example.com/a.jpg"
    assert visible.is_kz_video is False
    assert thumbnail_calls == ["hidden"]
    assert first.failed == 0

    second = await media_reclassification.reclassify_media_posts(
        session=db, platform=PlayerSocialPlatform.YOUTUBE
    )
    assert second.unchanged == 2
    assert len(metadata_calls) == 3


@pytest.mark.asyncio
async def test_reclassify_bilibili_contains_per_video_failures(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    link = await _create_link(db, PlayerSocialPlatform.BILIBILI)
    for video_id in ("BVgood", "BVfail"):
        db.add(
            MediaPost(
                player_social_link_id=link.id,
                player_steamid64=link.player_steamid64,
                platform=PlayerSocialPlatform.BILIBILI,
                external_video_id=video_id,
                title="Old title",
                url=f"https://www.bilibili.com/video/{video_id}",
                published_at=datetime.now(UTC),
            )
        )
    await db.commit()

    async def _detail(video_id: str) -> dict[str, Any]:
        if video_id == "BVfail":
            raise RuntimeError("temporary failure")
        return {"title": "Tag-only upload", "desc": "No keyword", "pic": None}

    async def _tags(video_id: str) -> list[str]:
        assert video_id == "BVgood"
        return ["KZ"]

    monkeypatch.setattr(media_reclassification, "fetch_bilibili_video_detail", _detail)
    monkeypatch.setattr(media_reclassification, "fetch_bilibili_video_tags", _tags)

    result = await media_reclassification.reclassify_media_posts(
        session=db, platform=PlayerSocialPlatform.BILIBILI
    )

    assert result.inspected == 2
    assert result.matched_by_reason[MediaMatchReason.TAG] == 1
    assert result.failed == 1
