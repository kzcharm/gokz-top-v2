from datetime import UTC, datetime

import pytest

from app.models import PlayerSocialPlatform
from app.services.player_webhooks import (
    BILIBILI_EMBED_COLOR,
    DISCORD_WEBHOOK_AVATAR_URL,
    DISCORD_WEBHOOK_USERNAME,
    TWITCH_EMBED_COLOR,
    DiscordWebhookStreamEvent,
    build_player_profile_url,
    build_discord_embed_payload,
    build_player_avatar_url,
    get_webhook_embed_color,
)

pytestmark = pytest.mark.asyncio


async def test_build_player_avatar_url_returns_full_size_avatar_url() -> None:
    avatar_hash = "a" * 40

    assert (
        build_player_avatar_url(avatar_hash)
        == f"https://avatars.steamstatic.com/{avatar_hash}_full.jpg"
    )


async def test_get_webhook_embed_color_matches_platform_branding() -> None:
    assert get_webhook_embed_color(PlayerSocialPlatform.TWITCH) == TWITCH_EMBED_COLOR
    assert (
        get_webhook_embed_color(PlayerSocialPlatform.BILIBILI)
        == BILIBILI_EMBED_COLOR
    )


async def test_build_discord_embed_payload_prefers_stream_preview_and_player_identity() -> None:
    event = DiscordWebhookStreamEvent(
        player_display_name="Streamer",
        player_avatar_hash="b" * 40,
        player_profile_url="https://gokz.top/profile/streamer",
        platform=PlayerSocialPlatform.BILIBILI,
        stream_url="https://live.bilibili.com/42",
        stream_title="Grinding maps",
        stream_preview_image_url="https://cdn.example.com/keyframe.jpg",
        channel_display_name="Streamer CN",
        viewer_count=88,
        started_at=datetime(2026, 5, 7, 12, 15, tzinfo=UTC),
    )

    payload = build_discord_embed_payload(event=event, is_test=False)

    embed = payload["embeds"][0]
    assert payload["username"] == DISCORD_WEBHOOK_USERNAME
    assert payload["avatar_url"] == DISCORD_WEBHOOK_AVATAR_URL
    assert embed["color"] == BILIBILI_EMBED_COLOR
    assert embed["url"] == "https://live.bilibili.com/42"
    assert embed["description"] == "Grinding maps"
    assert embed["author"]["name"] == "Streamer"
    assert embed["author"]["icon_url"] == build_player_avatar_url("b" * 40)
    assert embed["author"]["url"] == "https://gokz.top/profile/streamer"
    assert embed["image"]["url"] == "https://cdn.example.com/keyframe.jpg"
    assert embed["footer"]["text"] == "Bilibili"
    assert "fields" not in embed


async def test_build_discord_embed_payload_marks_test_notifications() -> None:
    event = DiscordWebhookStreamEvent(
        player_display_name="Streamer",
        player_avatar_hash=None,
        player_profile_url=None,
        platform=PlayerSocialPlatform.TWITCH,
        stream_url="https://www.twitch.tv/streamer",
        stream_title="Testing",
        started_at=datetime(2026, 5, 7, 12, 15, tzinfo=UTC),
    )

    payload = build_discord_embed_payload(event=event, is_test=True)

    embed = payload["embeds"][0]
    assert payload["avatar_url"] == DISCORD_WEBHOOK_AVATAR_URL
    assert embed["title"] == "Test notification: Streamer on Twitch"
    assert embed["footer"]["text"] == "Test Twitch stream notification"
    assert embed["color"] == TWITCH_EMBED_COLOR


async def test_build_player_profile_url_uses_profile_route() -> None:
    assert (
        build_player_profile_url(
            frontend_host="https://gokz.top/",
            player_identifier="my_alias",
        )
        == "https://gokz.top/profile/my_alias"
    )
