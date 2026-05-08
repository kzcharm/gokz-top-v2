from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote

import httpx

from app.models import PlayerSocialPlatform

STEAM_AVATAR_BASE_URL = "https://avatars.steamstatic.com"
DISCORD_WEBHOOK_AVATAR_URL = "https://r2.axekz.com/img/avatars/sakiko_computer.png"
DISCORD_WEBHOOK_USERNAME = "GOKZ.TOP"
TWITCH_EMBED_COLOR = 0x9146FF
BILIBILI_EMBED_COLOR = 0x00A1D6


@dataclass(frozen=True, slots=True)
class DiscordWebhookStreamEvent:
    player_display_name: str
    player_avatar_hash: str | None
    player_profile_url: str | None
    platform: PlayerSocialPlatform
    stream_url: str
    stream_title: str | None = None
    stream_preview_image_url: str | None = None
    channel_display_name: str | None = None
    viewer_count: int | None = None
    started_at: datetime | None = None


def build_player_avatar_url(avatar_hash: str | None) -> str | None:
    if not avatar_hash:
        return None
    normalized = avatar_hash.strip()
    if not normalized:
        return None
    return f"{STEAM_AVATAR_BASE_URL}/{normalized}_full.jpg"


def build_player_profile_url(*, frontend_host: str, player_identifier: str) -> str:
    return f"{frontend_host.rstrip('/')}/profile/{quote(player_identifier, safe='')}"


def get_webhook_embed_color(platform: PlayerSocialPlatform) -> int:
    if platform == PlayerSocialPlatform.BILIBILI:
        return BILIBILI_EMBED_COLOR
    if platform == PlayerSocialPlatform.TWITCH:
        return TWITCH_EMBED_COLOR
    raise ValueError(f"Unsupported webhook platform: {platform}")


def get_platform_label(platform: PlayerSocialPlatform) -> str:
    if platform == PlayerSocialPlatform.BILIBILI:
        return "Bilibili"
    if platform == PlayerSocialPlatform.TWITCH:
        return "Twitch"
    raise ValueError(f"Unsupported webhook platform: {platform}")


def build_discord_embed_payload(
    *,
    event: DiscordWebhookStreamEvent,
    is_test: bool,
) -> dict[str, object]:
    platform_label = get_platform_label(event.platform)
    avatar_url = build_player_avatar_url(event.player_avatar_hash)
    preview_image_url = event.stream_preview_image_url
    title_prefix = "Test notification" if is_test else "Stream started"
    footer_text = (
        f"Test {platform_label} stream notification"
        if is_test
        else platform_label
    )

    embed: dict[str, object] = {
        "title": f"{title_prefix}: {event.player_display_name} on {platform_label}",
        "url": event.stream_url,
        "color": get_webhook_embed_color(event.platform),
        "footer": {"text": footer_text},
    }
    if event.stream_title:
        embed["description"] = event.stream_title
    if avatar_url:
        embed["author"] = {
            "name": event.player_display_name,
            "icon_url": avatar_url,
            "url": event.player_profile_url or event.stream_url,
        }
    if preview_image_url:
        embed["image"] = {"url": preview_image_url}
    if event.started_at is not None:
        embed["timestamp"] = (
            event.started_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
        )

    return {
        "username": DISCORD_WEBHOOK_USERNAME,
        "avatar_url": DISCORD_WEBHOOK_AVATAR_URL,
        "embeds": [embed],
        "allowed_mentions": {"parse": []},
    }


async def send_discord_webhook(
    *,
    webhook_url: str,
    payload: dict[str, object],
) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(webhook_url, json=payload)
        response.raise_for_status()
