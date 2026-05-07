from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.models import LiveStreamState, Player, PlayerSocialLink, PlayerSocialPlatform
from app.services import live_streams
from app.services.live_streams import BilibiliLiveStatus
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


async def test_parse_bilibili_started_at_accepts_epoch_seconds() -> None:
    started_at = live_streams._parse_bilibili_started_at(1778153349)

    assert started_at == datetime(2026, 5, 7, 11, 29, 9, tzinfo=UTC)


async def test_check_bilibili_live_status_prefers_keyframe_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_fetch(_uids: list[int]) -> dict[str, object]:
        return {
            "123456": {
                "live_status": 1,
                "room_id": 42,
                "title": "On air",
                "online": 88,
                "keyframe": "https://i0.hdslb.com/bfs/live-key-frame/current.jpg",
                "cover_from_user": "https://i0.hdslb.com/bfs/live/cover.jpg",
                "uname": "Streamer CN",
                "live_time": 1778153349,
            },
            "654321": {
                "live_status": 1,
                "room_id": 84,
                "title": "Fallback cover",
                "online": 44,
                "keyframe": "",
                "cover_from_user": "https://i0.hdslb.com/bfs/live/fallback-cover.jpg",
                "uname": "Fallback Streamer",
                "live_time": "2026-05-07 12:00:00",
            },
        }

    monkeypatch.setattr(
        live_streams,
        "_fetch_bilibili_live_status_payload",
        _fake_fetch,
    )

    statuses = await live_streams.check_bilibili_live_status([123456, 654321])

    assert (
        statuses[123456].preview_image_url
        == "https://i0.hdslb.com/bfs/live/cover.jpg"
    )
    assert (
        statuses[123456].hover_preview_image_url
        == "https://i0.hdslb.com/bfs/live-key-frame/current.jpg"
    )
    assert (
        statuses[654321].preview_image_url
        == "https://i0.hdslb.com/bfs/live/fallback-cover.jpg"
    )
    assert statuses[654321].hover_preview_image_url is None


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
    platform: PlayerSocialPlatform,
    account_identifier: str,
    verified: bool,
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


async def _create_live_stream_state(
    db: AsyncSession,
    *,
    social_link_id,
    is_live: bool,
    last_checked_at: datetime,
    last_live_seen_at: datetime | None,
    last_live_started_at: datetime | None = None,
    last_stream_url: str | None = None,
    last_preview_image_url: str | None = None,
) -> LiveStreamState:
    state = LiveStreamState(
        social_link_id=social_link_id,
        is_live=is_live,
        last_checked_at=last_checked_at,
        last_live_seen_at=last_live_seen_at,
        last_live_started_at=last_live_started_at,
        last_stream_url=last_stream_url,
        last_preview_image_url=last_preview_image_url,
        updated_at=last_checked_at,
    )
    db.add(state)
    await db.commit()
    await db.refresh(state)
    return state


async def test_refresh_live_streams_uses_only_verified_bilibili_links(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = await _create_player(db, steamid64=random_steamid64(), name="Streamer")
    other_player = await _create_player(
        db,
        steamid64=random_steamid64(),
        name="Other Streamer",
    )
    verified_bilibili = await _create_social_link(
        db,
        player_steamid64=player.steamid64,
        platform=PlayerSocialPlatform.BILIBILI,
        account_identifier="123456",
        verified=True,
    )
    await _create_social_link(
        db,
        player_steamid64=other_player.steamid64,
        platform=PlayerSocialPlatform.BILIBILI,
        account_identifier="999999",
        verified=False,
    )
    await _create_social_link(
        db,
        player_steamid64=player.steamid64,
        platform=PlayerSocialPlatform.TWITCH,
        account_identifier="streamer",
        verified=True,
    )

    started_at = datetime(2026, 5, 6, 20, 0, tzinfo=UTC)

    async def _fake_check_bilibili_live_status(
        uids: list[int],
    ) -> dict[int, BilibiliLiveStatus]:
        assert uids == [123456]
        return {
            123456: BilibiliLiveStatus(
                is_live=True,
                stream_title="On air",
                viewer_count=88,
                preview_image_url="https://i0.hdslb.com/bfs/live/test-cover.jpg",
                hover_preview_image_url="https://i0.hdslb.com/bfs/live-key-frame/test.jpg",
                stream_url="https://live.bilibili.com/42",
                channel_display_name="Streamer CN",
                started_at=started_at,
            )
        }

    monkeypatch.setattr(
        live_streams,
        "check_bilibili_live_status",
        _fake_check_bilibili_live_status,
    )

    processed = await live_streams.refresh_live_streams_once(session=db)

    assert processed == 1
    state = await crud.get_live_stream_state(
        session=db,
        social_link_id=verified_bilibili.id,
    )
    assert state is not None
    assert state.is_live is True
    assert state.last_live_started_at == started_at
    assert state.last_live_seen_at is not None
    assert state.last_stream_title == "On air"
    assert state.last_stream_url == "https://live.bilibili.com/42"
    assert (
        state.last_preview_image_url
        == "https://i0.hdslb.com/bfs/live/test-cover.jpg"
    )
    assert (
        state.last_keyframe_image_url
        == "https://i0.hdslb.com/bfs/live-key-frame/test.jpg"
    )


async def test_refresh_live_streams_does_not_flip_live_state_on_transport_failure(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = await _create_player(db, steamid64=random_steamid64(), name="Streamer")
    link = await _create_social_link(
        db,
        player_steamid64=player.steamid64,
        platform=PlayerSocialPlatform.BILIBILI,
        account_identifier="123456",
        verified=True,
    )
    checked_at = datetime(2026, 5, 6, 20, 0, tzinfo=UTC)
    await _create_live_stream_state(
        db,
        social_link_id=link.id,
        is_live=True,
        last_checked_at=checked_at,
        last_live_seen_at=checked_at,
        last_live_started_at=checked_at,
        last_stream_url="https://live.bilibili.com/42",
    )

    async def _failing_check(_uids: list[int]) -> dict[int, BilibiliLiveStatus]:
        raise httpx.ConnectError("network down")

    monkeypatch.setattr(live_streams, "check_bilibili_live_status", _failing_check)

    with pytest.raises(httpx.ConnectError):
        await live_streams.refresh_live_streams_once(session=db)

    state = await crud.get_live_stream_state(session=db, social_link_id=link.id)
    assert state is not None
    assert state.is_live is True
    assert state.last_checked_at == checked_at
    assert state.last_live_seen_at == checked_at


async def test_read_live_stream_cards_prefers_most_recent_platform_for_offline_player(
    db: AsyncSession,
) -> None:
    player = await _create_player(
        db,
        steamid64=random_steamid64(),
        name="Dual Streamer",
        alias="Dual",
    )
    twitch_link = await _create_social_link(
        db,
        player_steamid64=player.steamid64,
        platform=PlayerSocialPlatform.TWITCH,
        account_identifier="dual-streamer",
        verified=True,
    )
    bilibili_link = await _create_social_link(
        db,
        player_steamid64=player.steamid64,
        platform=PlayerSocialPlatform.BILIBILI,
        account_identifier="123456",
        verified=True,
    )
    now = datetime(2026, 5, 7, 12, 0, tzinfo=UTC)
    await _create_live_stream_state(
        db,
        social_link_id=twitch_link.id,
        is_live=False,
        last_checked_at=now,
        last_live_seen_at=now - timedelta(days=3),
        last_stream_url="https://www.twitch.tv/dual-streamer",
    )
    await _create_live_stream_state(
        db,
        social_link_id=bilibili_link.id,
        is_live=False,
        last_checked_at=now,
        last_live_seen_at=now - timedelta(days=1),
        last_stream_url="https://live.bilibili.com/42",
    )

    cards = await crud.read_live_stream_cards(
        session=db,
        online=False,
        platforms=(
            PlayerSocialPlatform.BILIBILI,
            PlayerSocialPlatform.TWITCH,
        ),
        stale_after=timedelta(minutes=5),
        preview_url_resolver=lambda url: url,
    )

    assert len(cards) == 1
    assert cards[0].selected_platform == PlayerSocialPlatform.BILIBILI
    assert cards[0].stream_url == "https://live.bilibili.com/42"
    assert cards[0].last_streamed_at == now - timedelta(days=1)
