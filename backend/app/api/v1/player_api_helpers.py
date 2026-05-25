import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request

from app import crud
from app.api.deps import CurrentUser, SessionDep, user_has_role
from app.core.config import settings
from app.crud import player as player_crud
from app.models import (
    LiveStreamState,
    Player,
    PlayerSocialLink,
    PlayerSocialPlatform,
    UserRole,
)
from app.services.player_social_links import build_player_social_link_url
from app.services.player_webhooks import (
    DiscordWebhookStreamEvent,
    build_player_profile_url,
)

logger = logging.getLogger(__name__)


def parse_steamid64(steamid64: str) -> int:
    try:
        return int(steamid64)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid steamid64") from exc


async def get_player_or_404(*, session: SessionDep, identifier: str) -> Player:
    player = await player_crud.get_player_by_identifier(
        session=session,
        identifier=identifier,
    )
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return player


async def resolve_player_identifier_to_steamid64_or_404(
    *,
    session: SessionDep,
    identifier: str,
) -> int:
    steamid64 = await player_crud.resolve_player_identifier_to_steamid64(
        session=session,
        identifier=identifier,
    )
    if steamid64 is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return steamid64


def drop_null_group_ids(payload: dict[str, Any]) -> None:
    most_played_server = payload.get("most_played_server")
    if not isinstance(most_played_server, dict):
        return

    for period_key in ("all_time", "last_365_days"):
        period = most_played_server.get(period_key)
        if not isinstance(period, dict):
            continue
        entries = period.get("entries")
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and entry.get("group_id") is None:
                entry.pop("group_id", None)

    yearly = most_played_server.get("yearly")
    if not isinstance(yearly, dict):
        return

    for period in yearly.values():
        if not isinstance(period, dict):
            continue
        entries = period.get("entries")
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and entry.get("group_id") is None:
                entry.pop("group_id", None)


def ensure_current_user_owns_player(
    *,
    current_user: CurrentUser,
    target_steamid64: int,
) -> None:
    if current_user.steamid64 != target_steamid64:
        raise HTTPException(
            status_code=403,
            detail="You cannot modify another player's pinned records",
        )


def ensure_current_user_owns_social_link(
    *,
    current_user: CurrentUser,
    target_steamid64: int,
) -> None:
    if current_user.steamid64 != target_steamid64:
        raise HTTPException(
            status_code=403,
            detail="You cannot modify another player's social links",
        )


def ensure_current_user_can_check_own_ban_status(
    *,
    current_user: CurrentUser,
    target_steamid64: int,
) -> None:
    if current_user.steamid64 != target_steamid64:
        raise HTTPException(
            status_code=403,
            detail="You cannot check another player's ban status",
        )


def ensure_current_user_can_sync_own_friends(
    *,
    current_user: CurrentUser,
    target_steamid64: int,
) -> None:
    if current_user.steamid64 == target_steamid64:
        return
    if user_has_role(current_user, UserRole.SUPERUSER):
        return
    raise HTTPException(
        status_code=403,
        detail="You cannot sync another player's friends list",
    )


def ensure_current_user_can_manage_player_comment(
    *,
    current_user: CurrentUser,
    author_steamid64: int,
    target_steamid64: int,
) -> None:
    if current_user.steamid64 in {author_steamid64, target_steamid64}:
        return
    raise HTTPException(
        status_code=403,
        detail="You cannot delete this player comment",
    )


async def get_current_user_player_or_404(
    *,
    session: SessionDep,
    current_user: CurrentUser,
) -> Player:
    player = await crud.get_player_by_steamid64(
        session=session,
        steamid64=current_user.steamid64,
    )
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return player


async def get_current_user_webhook_or_404(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    webhook_id: uuid.UUID,
):
    webhook = await crud.get_player_webhook(session=session, id=webhook_id)
    if webhook is None or webhook.user_steamid64 != current_user.steamid64:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return webhook


def settings_return_path() -> str:
    return "/settings?tab=social-links"


def twitch_return_path() -> str:
    return "/settings?tab=social-links"


def twitch_callback_url(_request: Request) -> str:
    return (
        f"{settings.BACKEND_PUBLIC_URL.rstrip('/')}"
        f"{settings.API_V1_STR}"
        "/social-link-verifications/twitch/callback"
    )


async def build_test_webhook_event(
    *,
    session: SessionDep,
    player: Player,
) -> DiscordWebhookStreamEvent:
    player_identifier = player.custom_id or str(player.steamid64)
    links = await crud.list_player_social_links(
        session=session,
        player_steamid64=player.steamid64,
    )
    live_links = [
        link
        for link in links
        if link.verified
        and link.platform in {PlayerSocialPlatform.BILIBILI, PlayerSocialPlatform.TWITCH}
    ]

    candidates: list[tuple[PlayerSocialLink, LiveStreamState | None]] = []
    for link in live_links:
        candidates.append(
            (link, await crud.get_live_stream_state(session=session, social_link_id=link.id))
        )

    if candidates:
        best_link, best_state = max(
            candidates,
            key=lambda item: (
                item[1].last_live_seen_at if item[1] else datetime(1970, 1, 1, tzinfo=UTC),
                item[1].last_live_started_at
                if item[1]
                else datetime(1970, 1, 1, tzinfo=UTC),
            ),
        )
        preview_image_url = None
        if best_state is not None:
            preview_image_url = (
                best_state.last_keyframe_image_url or best_state.last_preview_image_url
            )
        return DiscordWebhookStreamEvent(
            player_display_name=player.alias or player.name,
            player_avatar_hash=player.avatar_hash,
            player_profile_url=build_player_profile_url(
                frontend_host=settings.FRONTEND_HOST,
                player_identifier=player_identifier,
            ),
            platform=best_link.platform,
            stream_url=(
                best_state.last_stream_url
                if best_state and best_state.last_stream_url
                else build_player_social_link_url(
                    platform=best_link.platform,
                    account_identifier=best_link.account_identifier,
                )
            ),
            stream_title=(
                best_state.last_stream_title
                if best_state and best_state.last_stream_title
                else "Webhook test notification"
            ),
            stream_preview_image_url=preview_image_url,
            channel_display_name=(
                best_state.last_channel_display_name
                if best_state and best_state.last_channel_display_name
                else best_link.account_identifier
            ),
            viewer_count=best_state.last_viewer_count if best_state else None,
            started_at=(
                best_state.last_live_started_at
                if best_state and best_state.last_live_started_at
                else datetime.now(UTC)
            ),
        )

    return DiscordWebhookStreamEvent(
        player_display_name=player.alias or player.name,
        player_avatar_hash=player.avatar_hash,
        player_profile_url=build_player_profile_url(
            frontend_host=settings.FRONTEND_HOST,
            player_identifier=player_identifier,
        ),
        platform=PlayerSocialPlatform.TWITCH,
        stream_url="https://www.twitch.tv/directory/category/kz-climb",
        stream_title="Webhook test notification",
        stream_preview_image_url=None,
        channel_display_name=None,
        viewer_count=None,
        started_at=datetime.now(UTC),
    )


def ensure_link_is_twitch_and_unverified(*, link: Any) -> None:
    if link.platform != PlayerSocialPlatform.TWITCH:
        raise HTTPException(
            status_code=422,
            detail="Only Twitch links can be verified with this flow",
        )
    if link.verified:
        raise HTTPException(status_code=409, detail="Social link is already verified")


def ensure_link_is_bilibili_and_unverified(*, link: Any) -> None:
    if link.platform != PlayerSocialPlatform.BILIBILI:
        raise HTTPException(
            status_code=422,
            detail="Only Bilibili links can be verified with this flow",
        )
    if link.verified:
        raise HTTPException(status_code=409, detail="Social link is already verified")
