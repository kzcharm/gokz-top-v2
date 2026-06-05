from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import LiveStreamState, Player, PlayerSocialLink, PlayerSocialPlatform
from app.models.utils import get_datetime_utc
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


async def _create_player(
    db: AsyncSession,
    *,
    steamid64: int,
    name: str,
    alias: str | None = None,
) -> Player:
    player = Player(steamid64=steamid64, name=name, alias=alias)
    db.add(player)
    await db.commit()
    await db.refresh(player)
    return player


async def _create_social_link(
    db: AsyncSession,
    *,
    player_steamid64: int,
    account_identifier: str,
    platform: PlayerSocialPlatform = PlayerSocialPlatform.BILIBILI,
    verified: bool = True,
) -> PlayerSocialLink:
    link = PlayerSocialLink(
        player_steamid64=player_steamid64,
        platform=platform,
        account_identifier=account_identifier,
        verified=verified,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return link


async def _create_state(
    db: AsyncSession,
    *,
    link_id,
    is_live: bool,
    last_checked_at,
    last_live_seen_at,
    stream_url: str,
    preview_url: str | None = None,
    hover_preview_url: str | None = None,
    viewer_count: int | None = None,
) -> LiveStreamState:
    state = LiveStreamState(
        social_link_id=link_id,
        is_live=is_live,
        last_checked_at=last_checked_at,
        last_live_seen_at=last_live_seen_at,
        last_live_started_at=last_live_seen_at if is_live else None,
        last_stream_url=stream_url,
        last_stream_title="Session title",
        last_preview_image_url=preview_url,
        last_keyframe_image_url=hover_preview_url,
        last_viewer_count=viewer_count,
        updated_at=last_checked_at,
    )
    db.add(state)
    await db.commit()
    await db.refresh(state)
    return state


async def test_read_live_streams_filters_online_and_offline(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    now = get_datetime_utc()
    live_player = await _create_player(
        db,
        steamid64=random_steamid64(),
        name="Live Player",
        alias="Live Alias",
    )
    offline_player = await _create_player(
        db,
        steamid64=random_steamid64(),
        name="Offline Player",
    )
    live_link = await _create_social_link(
        db,
        player_steamid64=live_player.steamid64,
        account_identifier="123456",
    )
    offline_link = await _create_social_link(
        db,
        player_steamid64=offline_player.steamid64,
        account_identifier="654321",
    )
    await _create_state(
        db,
        link_id=live_link.id,
        is_live=True,
        last_checked_at=now,
        last_live_seen_at=now,
        stream_url="https://live.bilibili.com/42",
        preview_url="https://i0.hdslb.com/bfs/live/live-cover.jpg",
        hover_preview_url="https://i0.hdslb.com/bfs/live-key-frame/live-frame.jpg",
        viewer_count=145612,
    )
    await _create_state(
        db,
        link_id=offline_link.id,
        is_live=True,
        last_checked_at=now - timedelta(minutes=10),
        last_live_seen_at=now - timedelta(days=1),
        stream_url="https://live.bilibili.com/84",
        preview_url="https://i0.hdslb.com/bfs/live/offline-cover.jpg",
        hover_preview_url="https://cdn.example.com/live/keyframes/bilibili/offline.jpg",
    )

    all_response = await client.get("/v1/live/streams")
    assert all_response.status_code == 200
    all_payload = all_response.json()
    assert all_payload["count"] == 2

    online_response = await client.get("/v1/live/streams", params={"online": True})
    assert online_response.status_code == 200
    online_payload = online_response.json()
    assert online_payload["count"] == 1
    assert online_payload["data"][0]["player"]["steamid64"] == str(
        live_player.steamid64
    )
    assert (
        online_payload["data"][0]["preview_image_url"]
        == "/v1/live/preview-image?url=https%3A%2F%2Fi0.hdslb.com%2Fbfs%2Flive%2Flive-cover.jpg"
    )
    assert (
        online_payload["data"][0]["hover_preview_image_url"]
        == "/v1/live/preview-image?url=https%3A%2F%2Fi0.hdslb.com%2Fbfs%2Flive-key-frame%2Flive-frame.jpg"
    )
    assert online_payload["data"][0]["last_viewer_count"] == 145612

    offline_response = await client.get(
        "/v1/live/streams",
        params={"online": False},
    )
    assert offline_response.status_code == 200
    offline_payload = offline_response.json()
    assert offline_payload["count"] == 1
    assert offline_payload["data"][0]["player"]["steamid64"] == str(
        offline_player.steamid64
    )
    assert offline_payload["data"][0]["is_live"] is False
    assert (
        offline_payload["data"][0]["preview_image_url"]
        == "https://cdn.example.com/live/keyframes/bilibili/offline.jpg"
    )
    assert offline_payload["data"][0]["hover_preview_image_url"] is None


async def test_read_live_streams_excludes_unobserved_links(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    player = await _create_player(db, steamid64=random_steamid64(), name="No History")
    await _create_social_link(
        db,
        player_steamid64=player.steamid64,
        account_identifier="777777",
    )

    response = await client.get("/v1/live/streams")

    assert response.status_code == 200
    assert response.json() == {"data": [], "count": 0}


async def test_read_live_streams_serializes_twitch_cards_and_recency(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    now = get_datetime_utc()
    live_player = await _create_player(
        db,
        steamid64=random_steamid64(),
        name="Twitch Player",
    )
    mixed_player = await _create_player(
        db,
        steamid64=random_steamid64(),
        name="Mixed Player",
    )
    twitch_live_link = await _create_social_link(
        db,
        player_steamid64=live_player.steamid64,
        account_identifier="twitch-player",
        platform=PlayerSocialPlatform.TWITCH,
    )
    mixed_twitch_link = await _create_social_link(
        db,
        player_steamid64=mixed_player.steamid64,
        account_identifier="mixed-twitch",
        platform=PlayerSocialPlatform.TWITCH,
    )
    mixed_bilibili_link = await _create_social_link(
        db,
        player_steamid64=mixed_player.steamid64,
        account_identifier="654321",
        platform=PlayerSocialPlatform.BILIBILI,
    )
    await _create_state(
        db,
        link_id=twitch_live_link.id,
        is_live=True,
        last_checked_at=now,
        last_live_seen_at=now,
        stream_url="https://www.twitch.tv/twitch-player",
        preview_url=(
            "https://static-cdn.jtvnw.net/previews-ttv/live_user_twitch-player-640x360.jpg"
        ),
        viewer_count=9123,
    )
    await _create_state(
        db,
        link_id=mixed_twitch_link.id,
        is_live=False,
        last_checked_at=now,
        last_live_seen_at=now - timedelta(days=1),
        stream_url="https://www.twitch.tv/mixed-twitch",
        preview_url=(
            "https://static-cdn.jtvnw.net/previews-ttv/live_user_mixed-twitch-640x360.jpg"
        ),
        hover_preview_url="https://cdn.example.com/live/keyframes/twitch/mixed-twitch.jpg",
        viewer_count=1200,
    )
    await _create_state(
        db,
        link_id=mixed_bilibili_link.id,
        is_live=False,
        last_checked_at=now,
        last_live_seen_at=now - timedelta(days=3),
        stream_url="https://live.bilibili.com/84",
        preview_url="https://i0.hdslb.com/bfs/live/mixed-cover.jpg",
    )

    live_response = await client.get("/v1/live/streams", params={"online": True})

    assert live_response.status_code == 200
    live_payload = live_response.json()
    assert live_payload["count"] == 1
    assert live_payload["data"][0]["selected_platform"] == "twitch"
    assert (
        live_payload["data"][0]["preview_image_url"]
        == "https://static-cdn.jtvnw.net/previews-ttv/live_user_twitch-player-640x360.jpg"
    )
    assert live_payload["data"][0]["hover_preview_image_url"] is None

    offline_response = await client.get(
        "/v1/live/streams",
        params={"online": False},
    )

    assert offline_response.status_code == 200
    offline_payload = offline_response.json()
    assert offline_payload["count"] == 1
    assert offline_payload["data"][0]["player"]["steamid64"] == str(
        mixed_player.steamid64
    )
    assert offline_payload["data"][0]["selected_platform"] == "twitch"
    assert offline_payload["data"][0]["stream_url"] == "https://www.twitch.tv/mixed-twitch"
    assert (
        offline_payload["data"][0]["preview_image_url"]
        == "https://cdn.example.com/live/keyframes/twitch/mixed-twitch.jpg"
    )
    assert offline_payload["data"][0]["hover_preview_image_url"] is None


async def test_proxy_live_preview_image_returns_bytes(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_fetch(_url: str) -> tuple[bytes, str]:
        return b"preview-bytes", "image/jpeg"

    monkeypatch.setattr("app.api.v1.live.fetch_live_preview_image", _fake_fetch)

    response = await client.get(
        "/v1/live/preview-image",
        params={"url": "https://i0.hdslb.com/bfs/live/live-cover.jpg"},
    )

    assert response.status_code == 200
    assert response.content == b"preview-bytes"
    assert response.headers["content-type"].startswith("image/jpeg")
