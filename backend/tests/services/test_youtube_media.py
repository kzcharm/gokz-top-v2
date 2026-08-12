from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.models import MediaPost, Player, PlayerSocialLink, PlayerSocialPlatform
from app.services import youtube_media
from tests.utils.utils import random_steamid64


class _Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


@pytest.mark.asyncio
async def test_fetch_youtube_posts_reads_the_channel_uploads_playlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class _Client:
        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def get(self, url: str, *, params: dict[str, object]) -> _Response:
            calls.append((url, params))
            if url == youtube_media.YOUTUBE_CHANNELS_URL:
                return _Response(
                    {
                        "items": [
                            {
                                "contentDetails": {
                                    "relatedPlaylists": {"uploads": "UU123"}
                                }
                            }
                        ]
                    }
                )
            if url == youtube_media.YOUTUBE_PLAYLIST_ITEMS_URL:
                return _Response(
                    {
                        "items": [
                            {
                                "id": "playlist-item",
                                "snippet": {"resourceId": {"videoId": "video-123"}},
                            }
                        ]
                    }
                )
            return _Response(
                {"items": [{"id": "video-123", "statistics": {"viewCount": "42"}}]}
            )

    monkeypatch.setattr(settings, "YOUTUBE_API_KEY", "youtube-key")
    monkeypatch.setattr(youtube_media.httpx, "AsyncClient", lambda **_: _Client())

    posts = await youtube_media.fetch_youtube_posts("@kzcis", page_size=5)

    assert posts == [
        {
            "id": "playlist-item",
            "snippet": {"resourceId": {"videoId": "video-123"}},
            "view_count": 42,
        }
    ]
    assert calls == [
        (
            youtube_media.YOUTUBE_CHANNELS_URL,
            {
                "part": "id,contentDetails",
                "key": "youtube-key",
                "forHandle": "@kzcis",
            },
        ),
        (
            youtube_media.YOUTUBE_PLAYLIST_ITEMS_URL,
            {
                "part": "snippet,contentDetails",
                "key": "youtube-key",
                "playlistId": "UU123",
                "maxResults": 5,
            },
        ),
        (
            youtube_media.YOUTUBE_VIDEOS_URL,
            {
                "part": "statistics",
                "key": "youtube-key",
                "id": "video-123",
            },
        ),
    ]


@pytest.mark.asyncio
async def test_refresh_youtube_websub_subscriptions_resolves_channels_and_signs_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[tuple[str, dict[str, str]]] = []
    link = PlayerSocialLink(
        player_steamid64=random_steamid64(),
        platform=PlayerSocialPlatform.YOUTUBE,
        account_identifier="@kzcis",
        verified=True,
    )

    class _Client:
        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def post(self, url: str, *, data: dict[str, str]) -> _Response:
            requests.append((url, data))
            return _Response({})

    async def _fetch_channel_id(account_identifier: str) -> str:
        assert account_identifier == "@kzcis"
        return "UC12345678901234567890AB"

    monkeypatch.setattr(settings, "BACKEND_PUBLIC_URL", "https://api.example.com")
    monkeypatch.setattr(settings, "YOUTUBE_WEBSUB_ENABLED", True)
    monkeypatch.setattr(settings, "YOUTUBE_WEBSUB_SECRET", "websub-secret")
    monkeypatch.setattr(youtube_media, "fetch_youtube_channel_id", _fetch_channel_id)
    monkeypatch.setattr(youtube_media.httpx, "AsyncClient", lambda **_: _Client())

    assert await youtube_media.refresh_youtube_websub_subscriptions(links=[link])
    assert requests == [
        (
            youtube_media.YOUTUBE_WEBSUB_HUB_URL,
            {
                "hub.mode": "subscribe",
                "hub.topic": (
                    "https://www.youtube.com/xml/feeds/videos.xml?"
                    "channel_id=UC12345678901234567890AB"
                ),
                "hub.callback": "https://api.example.com/v1/webhooks/youtube",
                "hub.verify": "async",
                "hub.secret": "websub-secret",
                "hub.lease_seconds": str(youtube_media.YOUTUBE_WEBSUB_LEASE_SECONDS),
            },
        )
    ]


@pytest.mark.asyncio
async def test_refresh_youtube_websub_subscriptions_is_disabled_without_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "YOUTUBE_WEBSUB_ENABLED", False)
    monkeypatch.setattr(settings, "YOUTUBE_WEBSUB_SECRET", None)

    assert await youtube_media.refresh_youtube_websub_subscriptions(links=[])


@pytest.mark.asyncio
async def test_sync_youtube_media_creates_posts_for_verified_youtube_links(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = Player(steamid64=random_steamid64(), name="Video Player")
    db.add(player)
    await db.commit()
    link = PlayerSocialLink(
        player_steamid64=player.steamid64,
        platform=PlayerSocialPlatform.YOUTUBE,
        account_identifier="@videoplayer",
        verified=True,
    )
    db.add(link)
    await db.commit()

    async def _fetch_posts(_: str) -> list[dict[str, Any]]:
        return [
            {
                "snippet": {
                    "title": "Recent KZ run",
                    "description": "A precise run",
                    "resourceId": {"videoId": "abc123"},
                    "thumbnails": {"high": {"url": "https://example.com/thumb.jpg"}},
                },
                "contentDetails": {"videoPublishedAt": "2026-08-10T12:00:00Z"},
                "view_count": 42,
            }
        ]

    async def _cache_thumbnail(*, video_id: str, raw_url: str | None) -> str | None:
        assert video_id == "abc123"
        assert raw_url == "https://example.com/thumb.jpg"
        return raw_url

    monkeypatch.setattr(youtube_media, "fetch_youtube_posts", _fetch_posts)
    monkeypatch.setattr(youtube_media, "cache_youtube_thumbnail", _cache_thumbnail)

    assert await youtube_media.sync_youtube_media_once(session=db) == 1

    post = (await db.exec(select(MediaPost))).one()
    assert post is not None
    assert post.platform == PlayerSocialPlatform.YOUTUBE
    assert post.external_video_id == "abc123"
    assert post.url == "https://www.youtube.com/watch?v=abc123"
    assert post.published_at == datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
    assert post.view_count == 42


@pytest.mark.asyncio
async def test_media_feed_returns_youtube_and_bilibili_posts(db: AsyncSession) -> None:
    player = Player(steamid64=random_steamid64(), name="Media Player")
    db.add(player)
    await db.commit()
    now = datetime.now(UTC)
    youtube_link = PlayerSocialLink(
        player_steamid64=player.steamid64,
        platform=PlayerSocialPlatform.YOUTUBE,
        account_identifier="@mediaplayer",
        verified=True,
    )
    bilibili_link = PlayerSocialLink(
        player_steamid64=player.steamid64,
        platform=PlayerSocialPlatform.BILIBILI,
        account_identifier="123456",
        verified=True,
    )
    db.add(youtube_link)
    db.add(bilibili_link)
    await db.commit()
    db.add(
        MediaPost(
            player_social_link_id=youtube_link.id,
            player_steamid64=player.steamid64,
            platform=PlayerSocialPlatform.YOUTUBE,
            external_video_id="youtube-video",
            title="YouTube video",
            url="https://www.youtube.com/watch?v=youtube-video",
            published_at=now,
        )
    )
    db.add(
        MediaPost(
            player_social_link_id=bilibili_link.id,
            player_steamid64=player.steamid64,
            platform=PlayerSocialPlatform.BILIBILI,
            external_video_id="bilibili-video",
            title="Bilibili video",
            url="https://www.bilibili.com/video/bilibili-video",
            published_at=now - timedelta(seconds=1),
        )
    )
    await db.commit()

    response = await crud.read_media_posts(
        session=db,
        cursor=None,
        limit=24,
        steamid64=None,
        from_=None,
        to=None,
    )

    assert [post.external_video_id for post in response.data] == [
        "youtube-video",
        "bilibili-video",
    ]
