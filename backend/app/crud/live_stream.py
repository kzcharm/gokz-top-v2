from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.crud.player import load_player_roles_by_steamid64
from app.models import (
    LiveStreamCardPublic,
    LiveStreamPlayerPublic,
    LiveStreamState,
    Player,
    PlayerSocialLink,
    PlayerSocialPlatform,
    UserRole,
    get_datetime_utc,
)
from app.services.player_social_links import (
    SOCIAL_PLATFORM_ORDER,
    build_player_social_link_url,
)


@dataclass(frozen=True, slots=True)
class LiveStreamCandidate:
    link: PlayerSocialLink
    player: Player
    state: LiveStreamState
    is_live: bool


def _platform_order(platform: PlayerSocialPlatform) -> int:
    try:
        return SOCIAL_PLATFORM_ORDER.index(platform)
    except ValueError:
        return len(SOCIAL_PLATFORM_ORDER)


def _is_effectively_live(
    *,
    state: LiveStreamState | None,
    now: datetime,
    stale_after: timedelta,
) -> bool:
    if state is None or state.is_live is not True or state.last_checked_at is None:
        return False
    return state.last_checked_at >= now - stale_after


async def list_verified_live_stream_links(
    *,
    session: AsyncSession,
    platforms: Sequence[PlayerSocialPlatform],
) -> list[PlayerSocialLink]:
    statement = (
        select(PlayerSocialLink)
        .where(
            col(PlayerSocialLink.verified).is_(True),
            col(PlayerSocialLink.platform).in_(list(platforms)),
        )
        .order_by(
            col(PlayerSocialLink.platform).asc(),
            col(PlayerSocialLink.player_steamid64).asc(),
            col(PlayerSocialLink.created_at).asc(),
        )
    )
    return list((await session.exec(statement)).all())


async def get_live_stream_state(
    *,
    session: AsyncSession,
    social_link_id: uuid.UUID,
) -> LiveStreamState | None:
    return await session.get(LiveStreamState, social_link_id)


async def upsert_live_stream_state(
    *,
    session: AsyncSession,
    social_link_id: uuid.UUID,
    checked_at: datetime,
    is_live: bool,
    stream_url: str | None = None,
    stream_title: str | None = None,
    preview_image_url: str | None = None,
    hover_preview_image_url: str | None = None,
    channel_display_name: str | None = None,
    viewer_count: int | None = None,
    update_viewer_count: bool = False,
    started_at: datetime | None = None,
    commit: bool = True,
) -> LiveStreamState:
    state = await session.get(LiveStreamState, social_link_id)
    if state is None:
        state = LiveStreamState(social_link_id=social_link_id)

    state.last_checked_at = checked_at
    state.is_live = is_live
    state.updated_at = checked_at
    if update_viewer_count:
        state.last_viewer_count = viewer_count

    if is_live:
        state.last_live_seen_at = checked_at
        if started_at is not None:
            state.last_live_started_at = started_at
        if stream_url is not None:
            state.last_stream_url = stream_url
        if stream_title is not None:
            state.last_stream_title = stream_title
        if preview_image_url is not None:
            state.last_preview_image_url = preview_image_url
        if hover_preview_image_url is not None:
            state.last_keyframe_image_url = hover_preview_image_url
        if channel_display_name is not None:
            state.last_channel_display_name = channel_display_name

    session.add(state)
    if commit:
        await session.commit()
        await session.refresh(state)
    else:
        await session.flush()
    return state


async def read_live_stream_cards(
    *,
    session: AsyncSession,
    online: bool | None,
    platforms: Sequence[PlayerSocialPlatform],
    stale_after: timedelta,
    preview_url_resolver: Callable[[str], str],
) -> list[LiveStreamCardPublic]:
    now = get_datetime_utc()
    statement = (
        select(PlayerSocialLink, Player, LiveStreamState)
        .join(
            Player,
            col(Player.steamid64) == col(PlayerSocialLink.player_steamid64),
        )
        .outerjoin(
            LiveStreamState,
            col(LiveStreamState.social_link_id) == col(PlayerSocialLink.id),
        )
        .where(
            col(PlayerSocialLink.verified).is_(True),
            col(PlayerSocialLink.platform).in_(list(platforms)),
        )
        .order_by(
            col(PlayerSocialLink.player_steamid64).asc(),
            col(PlayerSocialLink.platform).asc(),
            col(PlayerSocialLink.created_at).asc(),
        )
    )
    rows = list((await session.exec(statement)).all())
    roles_by_steamid64 = await load_player_roles_by_steamid64(
        session=session,
        steamid64s=[player.steamid64 for _link, player, _state in rows],
    )

    candidates_by_player: dict[int, list[LiveStreamCandidate]] = defaultdict(list)
    for link, player, state in rows:
        effective_live = _is_effectively_live(
            state=state,
            now=now,
            stale_after=stale_after,
        )
        if effective_live:
            include = online is not False
        else:
            include = (
                online is not True
                and state is not None
                and state.last_live_seen_at is not None
            )
        if not include or state is None:
            continue

        candidates_by_player[player.steamid64].append(
            LiveStreamCandidate(
                link=link,
                player=player,
                state=state,
                is_live=effective_live,
            )
        )

    cards = [
        _to_live_stream_card_public(
            candidate=_pick_best_candidate(candidates),
            preview_url_resolver=preview_url_resolver,
            roles_by_steamid64=roles_by_steamid64,
        )
        for candidates in candidates_by_player.values()
        if candidates
    ]
    cards.sort(
        key=lambda card: (
            0 if card.is_live else 1,
            -(
                (
                    card.started_at
                    or card.last_streamed_at
                    or datetime(1970, 1, 1, tzinfo=UTC)
                ).timestamp()
            ),
            card.player.steamid64,
        )
    )
    return cards


def _pick_best_candidate(
    candidates: Sequence[LiveStreamCandidate],
) -> LiveStreamCandidate:
    live_candidates = [candidate for candidate in candidates if candidate.is_live]
    if live_candidates:
        return max(
            live_candidates,
            key=lambda candidate: (
                candidate.state.last_live_started_at
                or candidate.state.last_live_seen_at
                or datetime(1970, 1, 1, tzinfo=UTC),
                -_platform_order(candidate.link.platform),
            ),
        )

    return max(
        candidates,
        key=lambda candidate: (
            candidate.state.last_live_seen_at or datetime(1970, 1, 1, tzinfo=UTC),
            -_platform_order(candidate.link.platform),
        ),
    )


def _to_live_stream_card_public(
    *,
    candidate: LiveStreamCandidate,
    preview_url_resolver: Callable[[str], str],
    roles_by_steamid64: dict[int, list[UserRole]],
) -> LiveStreamCardPublic:
    raw_preview_image_url = candidate.state.last_preview_image_url
    return LiveStreamCardPublic(
        player=LiveStreamPlayerPublic(
            steamid64=str(candidate.player.steamid64),
            name=candidate.player.name,
            alias=candidate.player.alias,
            avatar_hash=candidate.player.avatar_hash,
            country=candidate.player.country,
            custom_id=candidate.player.custom_id,
            roles=roles_by_steamid64.get(candidate.player.steamid64),
        ),
        selected_platform=candidate.link.platform,
        selected_platform_account_identifier=candidate.link.account_identifier,
        is_live=candidate.is_live,
        stream_url=(
            candidate.state.last_stream_url
            or build_player_social_link_url(
                platform=candidate.link.platform,
                account_identifier=candidate.link.account_identifier,
            )
        ),
        last_viewer_count=candidate.state.last_viewer_count,
        preview_image_url=(
            preview_url_resolver(raw_preview_image_url)
            if raw_preview_image_url
            else None
        ),
        hover_preview_image_url=(
            preview_url_resolver(candidate.state.last_keyframe_image_url)
            if candidate.is_live and candidate.state.last_keyframe_image_url
            else None
        ),
        stream_title=candidate.state.last_stream_title,
        started_at=(
            candidate.state.last_live_started_at if candidate.is_live else None
        ),
        last_streamed_at=candidate.state.last_live_seen_at,
    )
