from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.crud import media_post
from app.models import MediaPost, Player, PlayerSocialLink, PlayerSocialPlatform
from app.models.utils import get_datetime_utc
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


async def test_read_media_posts_proxies_bilibili_thumbnails(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    player = Player(steamid64=random_steamid64(), name="Media Player")
    db.add(player)
    await db.commit()
    link = PlayerSocialLink(
        player_steamid64=player.steamid64,
        platform=PlayerSocialPlatform.BILIBILI,
        account_identifier="12345",
        verified=True,
    )
    db.add(link)
    await db.commit()
    post = MediaPost(
        player_social_link_id=link.id,
        player_steamid64=player.steamid64,
        platform=PlayerSocialPlatform.BILIBILI,
        external_video_id="BV1thumbnail",
        title="Bilibili thumbnail",
        url="https://www.bilibili.com/video/BV1thumbnail",
        thumbnail_url="http://i0.hdslb.com/bfs/archive/thumbnail.jpg",
        published_at=get_datetime_utc(),
    )
    db.add(post)
    await db.commit()

    response = await client.get("/v1/media/posts")

    assert response.status_code == 200
    assert response.json()["data"][0]["thumbnail_url"] == (
        f"{settings.BACKEND_PUBLIC_URL}/v1/media/thumbnail?"
        "url=http%3A%2F%2Fi0.hdslb.com%2Fbfs%2Farchive%2Fthumbnail.jpg"
    )


async def test_proxy_bilibili_thumbnail_returns_bytes(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_fetch(_url: str) -> tuple[bytes, str]:
        return b"thumbnail-bytes", "image/jpeg"

    monkeypatch.setattr("app.api.v1.media.fetch_bilibili_thumbnail", _fake_fetch)

    response = await client.get(
        "/v1/media/thumbnail",
        params={"url": "https://i0.hdslb.com/bfs/archive/thumbnail.jpg"},
    )

    assert response.status_code == 200
    assert response.content == b"thumbnail-bytes"
    assert response.headers["content-type"].startswith("image/jpeg")


async def test_read_media_posts_serves_cached_bilibili_thumbnail_directly(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    player = Player(steamid64=random_steamid64(), name="Media Player")
    db.add(player)
    await db.commit()
    link = PlayerSocialLink(
        player_steamid64=player.steamid64,
        platform=PlayerSocialPlatform.BILIBILI,
        account_identifier="12345",
        verified=True,
    )
    db.add(link)
    await db.commit()
    thumbnail_url = "https://cdn.example.com/media/thumbnails/bilibili/BV1cached.jpg"
    db.add(
        MediaPost(
            player_social_link_id=link.id,
            player_steamid64=player.steamid64,
            platform=PlayerSocialPlatform.BILIBILI,
            external_video_id="BV1cached",
            title="Cached Bilibili thumbnail",
            url="https://www.bilibili.com/video/BV1cached",
            thumbnail_url=thumbnail_url,
            published_at=get_datetime_utc(),
        )
    )
    await db.commit()

    response = await client.get("/v1/media/posts")

    assert response.status_code == 200
    assert response.json()["data"][0]["thumbnail_url"] == thumbnail_url


async def test_proxy_bilibili_thumbnail_rejects_untrusted_host(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/v1/media/thumbnail",
        params={"url": "https://example.com/thumbnail.jpg"},
    )

    assert response.status_code == 400


async def test_refresh_media_post_view_counts_updates_stale_posts_by_platform(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = Player(steamid64=random_steamid64(), name="Media Player")
    db.add(player)
    await db.commit()
    youtube_link = PlayerSocialLink(
        player_steamid64=player.steamid64,
        platform=PlayerSocialPlatform.YOUTUBE,
        account_identifier="@media-player",
        verified=True,
    )
    bilibili_link = PlayerSocialLink(
        player_steamid64=player.steamid64,
        platform=PlayerSocialPlatform.BILIBILI,
        account_identifier="12345",
        verified=True,
    )
    db.add(youtube_link)
    db.add(bilibili_link)
    await db.commit()

    now = get_datetime_utc()
    stale_youtube = MediaPost(
        player_social_link_id=youtube_link.id,
        player_steamid64=player.steamid64,
        platform=PlayerSocialPlatform.YOUTUBE,
        external_video_id="stale-video",
        title="Stale video",
        url="https://youtube.example/stale-video",
        published_at=now,
        view_count=10,
        last_checked_at=now - timedelta(hours=2),
    )
    fresh_youtube = MediaPost(
        player_social_link_id=youtube_link.id,
        player_steamid64=player.steamid64,
        platform=PlayerSocialPlatform.YOUTUBE,
        external_video_id="fresh-video",
        title="Fresh video",
        url="https://youtube.example/fresh-video",
        published_at=now,
        view_count=20,
        last_checked_at=now,
    )
    bilibili_post = MediaPost(
        player_social_link_id=bilibili_link.id,
        player_steamid64=player.steamid64,
        platform=PlayerSocialPlatform.BILIBILI,
        external_video_id="bilibili-video",
        title="Bilibili video",
        url="https://bilibili.example/bilibili-video",
        published_at=now,
        view_count=30,
        last_checked_at=now - timedelta(hours=2),
    )
    db.add(stale_youtube)
    db.add(fresh_youtube)
    db.add(bilibili_post)
    await db.commit()

    requested_youtube_ids: list[str] = []
    requested_bilibili_ids: list[str] = []

    async def fetch_view_counts(video_ids: list[str]) -> dict[str, int]:
        requested_youtube_ids.extend(video_ids)
        return {"stale-video": 99}

    async def fetch_bilibili_view_counts(video_ids: list[str]) -> dict[str, int]:
        requested_bilibili_ids.extend(video_ids)
        return {"bilibili-video": 199}

    monkeypatch.setattr(
        media_post, "fetch_youtube_video_view_counts", fetch_view_counts
    )
    monkeypatch.setattr(
        media_post, "fetch_bilibili_video_view_counts", fetch_bilibili_view_counts
    )

    response = await client.post(
        "/v1/media/posts/view-counts",
        json={
            "post_ids": [
                str(stale_youtube.id),
                str(stale_youtube.id),
                str(fresh_youtube.id),
                str(bilibili_post.id),
            ]
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "data": [
            {"id": str(stale_youtube.id), "view_count": 99},
            {"id": str(bilibili_post.id), "view_count": 199},
        ]
    }
    assert requested_youtube_ids == ["stale-video"]
    assert requested_bilibili_ids == ["bilibili-video"]
    await db.refresh(stale_youtube)
    await db.refresh(fresh_youtube)
    await db.refresh(bilibili_post)
    assert stale_youtube.view_count == 99
    assert stale_youtube.last_checked_at > now - timedelta(minutes=1)
    assert fresh_youtube.view_count == 20
    assert bilibili_post.view_count == 199


async def test_refresh_media_post_view_counts_preserves_cached_values_on_failure(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = Player(steamid64=random_steamid64(), name="Media Player")
    db.add(player)
    await db.commit()
    link = PlayerSocialLink(
        player_steamid64=player.steamid64,
        platform=PlayerSocialPlatform.YOUTUBE,
        account_identifier="@media-player",
        verified=True,
    )
    db.add(link)
    await db.commit()
    checked_at = datetime.now(UTC) - timedelta(hours=2)
    post = MediaPost(
        player_social_link_id=link.id,
        player_steamid64=player.steamid64,
        platform=PlayerSocialPlatform.YOUTUBE,
        external_video_id="video",
        title="Video",
        url="https://youtube.example/video",
        published_at=datetime.now(UTC),
        view_count=10,
        last_checked_at=checked_at,
    )
    db.add(post)
    await db.commit()

    async def fail_refresh(_: list[str]) -> dict[str, int]:
        raise RuntimeError("YouTube unavailable")

    monkeypatch.setattr(media_post, "fetch_youtube_video_view_counts", fail_refresh)

    response = await client.post(
        "/v1/media/posts/view-counts", json={"post_ids": [str(post.id)]}
    )

    assert response.status_code == 200
    assert response.json() == {"data": []}
    await db.refresh(post)
    assert post.view_count == 10
    assert post.last_checked_at == checked_at
    assert post.last_error == "YouTube unavailable"
