from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import delete, func
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.crud.player import get_player_display_name
from app.models import (
    ContentReaction,
    GitHubRelease,
    MapReview,
    MediaPost,
    Player,
    PlayerSocialLink,
    PlayerSocialPlatform,
    Poll,
    ReactionEmojiPublic,
    ReactionGroupPublic,
    ReactionPlayerPublic,
    ReactionSummaryPublic,
    ReactionTargetType,
    ReactionUserPublic,
    ReactionUsersPublic,
    RecentWrEventCache,
    generate_uuid7,
    get_datetime_utc,
)

REACTION_EMOJIS: tuple[ReactionEmojiPublic, ...] = (
    ReactionEmojiPublic(key="unicode:fire", name="Fire", value="🔥"),
    ReactionEmojiPublic(key="unicode:thumbs_up", name="Thumbs up", value="👍"),
    ReactionEmojiPublic(key="unicode:heart", name="Heart", value="❤️"),
    ReactionEmojiPublic(key="unicode:tada", name="Celebrate", value="🎉"),
    ReactionEmojiPublic(key="unicode:trophy", name="Trophy", value="🏆"),
    ReactionEmojiPublic(key="unicode:joy", name="Joy", value="😂"),
    ReactionEmojiPublic(key="unicode:eyes", name="Eyes", value="👀"),
    ReactionEmojiPublic(key="unicode:open_mouth", name="Surprised", value="😮"),
    ReactionEmojiPublic(key="unicode:cry", name="Sad", value="😢"),
    ReactionEmojiPublic(key="unicode:thinking", name="Thinking", value="🤔"),
    ReactionEmojiPublic(key="unicode:skull", name="Skull", value="💀"),
    ReactionEmojiPublic(key="unicode:thumbs_down", name="Thumbs down", value="👎"),
)
REACTION_EMOJI_BY_KEY = {emoji.key: emoji for emoji in REACTION_EMOJIS}


def parse_reaction_target_id(
    target_type: ReactionTargetType, target_id: str
) -> uuid.UUID | int:
    try:
        if target_type == ReactionTargetType.RELEASE:
            parsed = int(target_id)
            if parsed <= 0:
                raise ValueError
            return parsed
        return uuid.UUID(target_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid reaction target ID") from exc


def _serialize_reaction_target_id(target_id: uuid.UUID | int) -> str:
    return str(target_id)


def get_reaction_emoji(emoji_key: str) -> ReactionEmojiPublic:
    emoji = REACTION_EMOJI_BY_KEY.get(emoji_key)
    if emoji is None:
        raise ValueError("Unsupported emoji")
    return emoji


def _comment_exists(review: MapReview) -> bool:
    comment = review.content.get("comment")
    return (
        isinstance(comment, dict)
        and isinstance(comment.get("text"), str)
        and bool(comment["text"].strip())
    )


async def reaction_target_exists(
    *,
    session: AsyncSession,
    target_type: ReactionTargetType,
    target_id: uuid.UUID | int,
) -> bool:
    if target_type == ReactionTargetType.MEDIA_POST:
        row = (
            await session.exec(
                select(MediaPost.id)
                .join(
                    PlayerSocialLink,
                    col(PlayerSocialLink.id) == col(MediaPost.player_social_link_id),
                )
                .where(
                    col(MediaPost.id) == target_id,
                    col(MediaPost.is_kz_video).is_(True),
                    col(MediaPost.available).is_(True),
                    col(MediaPost.platform).in_(
                        [PlayerSocialPlatform.YOUTUBE, PlayerSocialPlatform.BILIBILI]
                    ),
                    col(PlayerSocialLink.show_on_site).is_(True),
                )
            )
        ).first()
        return row is not None
    if target_type == ReactionTargetType.RECENT_WR:
        return (
            await session.exec(
                select(RecentWrEventCache.record_uuid)
                .where(col(RecentWrEventCache.record_uuid) == target_id)
                .limit(1)
            )
        ).first() is not None
    if target_type == ReactionTargetType.MAP_REVIEW_COMMENT:
        review = await session.get(MapReview, target_id)
        return review is not None and _comment_exists(review)
    if target_type == ReactionTargetType.POLL:
        poll = await session.get(Poll, target_id)
        return poll is not None and poll.deleted_at is None
    release = await session.get(GitHubRelease, target_id)
    return release is not None and release.is_listed


async def load_reaction_summaries(
    *,
    session: AsyncSession,
    target_type: ReactionTargetType,
    target_ids: Iterable[uuid.UUID | int],
    viewer_steamid64: int | None,
) -> dict[uuid.UUID | int, ReactionSummaryPublic]:
    unique_target_ids = list(dict.fromkeys(target_ids))
    if not unique_target_ids:
        return {}
    content_ids = [
        _serialize_reaction_target_id(target_id) for target_id in unique_target_ids
    ]
    count_rows = (
        await session.exec(
            select(ContentReaction.content_id, ContentReaction.emoji_key, func.count())
            .where(
                col(ContentReaction.content_type) == target_type.value,
                col(ContentReaction.content_id).in_(content_ids),
            )
            .group_by(ContentReaction.content_id, ContentReaction.emoji_key)
        )
    ).all()
    viewer_rows: dict[tuple[str, str], uuid.UUID] = {}
    if viewer_steamid64 is not None:
        rows = (
            await session.exec(
                select(
                    ContentReaction.content_id,
                    ContentReaction.emoji_key,
                    ContentReaction.id,
                ).where(
                    col(ContentReaction.content_type) == target_type.value,
                    col(ContentReaction.content_id).in_(content_ids),
                    col(ContentReaction.user_steamid64) == viewer_steamid64,
                )
            )
        ).all()
        viewer_rows = {
            (target_id, emoji_key): reaction_id
            for target_id, emoji_key, reaction_id in rows
        }

    grouped: dict[str, dict[str, int]] = {}
    for content_id, emoji_key, count in count_rows:
        grouped.setdefault(content_id, {})[emoji_key] = int(count)
    result: dict[uuid.UUID | int, ReactionSummaryPublic] = {}
    for target_id in unique_target_ids:
        content_id = _serialize_reaction_target_id(target_id)
        counts = grouped.get(content_id, {})
        groups = []
        for emoji in REACTION_EMOJIS:
            count = counts.get(emoji.key, 0)
            if count == 0:
                continue
            reaction_id = viewer_rows.get((content_id, emoji.key))
            groups.append(
                ReactionGroupPublic(
                    emoji=emoji,
                    count=count,
                    reacted_by_me=reaction_id is not None,
                    reaction_id=reaction_id,
                )
            )
        result[target_id] = ReactionSummaryPublic(groups=groups)
    return result


async def create_content_reaction(
    *,
    session: AsyncSession,
    target_type: ReactionTargetType,
    target_id: uuid.UUID | int,
    user_steamid64: int,
    emoji_key: str,
) -> ReactionSummaryPublic:
    get_reaction_emoji(emoji_key)
    if not await reaction_target_exists(
        session=session, target_type=target_type, target_id=target_id
    ):
        raise LookupError("Reaction target not found")
    values = {
        "id": generate_uuid7(),
        "user_steamid64": user_steamid64,
        "emoji_key": emoji_key,
        "created_at": get_datetime_utc(),
        "content_type": target_type.value,
        "content_id": _serialize_reaction_target_id(target_id),
    }
    statement = (
        insert(ContentReaction)
        .values(**values)
        .on_conflict_do_nothing(constraint="uq_content_reaction_user_emoji_target")
    )
    await session.exec(statement)
    await session.commit()
    return (
        await load_reaction_summaries(
            session=session,
            target_type=target_type,
            target_ids=[target_id],
            viewer_steamid64=user_steamid64,
        )
    )[target_id]


async def delete_content_reaction(
    *, session: AsyncSession, reaction_id: uuid.UUID, user_steamid64: int
) -> tuple[ReactionTargetType, uuid.UUID | int]:
    reaction = await session.get(ContentReaction, reaction_id)
    if reaction is None or reaction.user_steamid64 != user_steamid64:
        raise LookupError("Reaction not found")
    target_type = ReactionTargetType(reaction.content_type)
    target_id = parse_reaction_target_id(target_type, reaction.content_id)
    await session.delete(reaction)
    await session.commit()
    return target_type, target_id


async def read_reaction_users(
    *,
    session: AsyncSession,
    target_type: ReactionTargetType,
    target_id: uuid.UUID | int,
    emoji_key: str,
    offset: int,
    limit: int,
) -> ReactionUsersPublic:
    get_reaction_emoji(emoji_key)
    if not await reaction_target_exists(
        session=session, target_type=target_type, target_id=target_id
    ):
        raise LookupError("Reaction target not found")
    filters = [
        col(ContentReaction.content_type) == target_type.value,
        col(ContentReaction.content_id) == _serialize_reaction_target_id(target_id),
        col(ContentReaction.emoji_key) == emoji_key,
    ]
    count = int(
        (
            await session.exec(
                select(func.count()).select_from(ContentReaction).where(*filters)
            )
        ).one()
    )
    rows = (
        await session.exec(
            select(ContentReaction, Player)
            .join(Player, col(Player.steamid64) == col(ContentReaction.user_steamid64))
            .where(*filters)
            .order_by(
                col(ContentReaction.created_at).desc(), col(ContentReaction.id).desc()
            )
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return ReactionUsersPublic(
        data=[
            ReactionUserPublic(
                player=ReactionPlayerPublic(
                    steamid64=str(player.steamid64),
                    display_name=get_player_display_name(player=player),
                    avatar_hash=player.avatar_hash,
                ),
                created_at=reaction.created_at,
            )
            for reaction, player in rows
        ],
        count=count,
    )


async def delete_map_review_reactions(
    *, session: AsyncSession, review_ids: Iterable[uuid.UUID]
) -> None:
    ids = list(review_ids)
    await delete_content_reactions_for_targets(
        session=session,
        target_type=ReactionTargetType.MAP_REVIEW_COMMENT,
        target_ids=ids,
    )


async def delete_poll_reactions(*, session: AsyncSession, poll_id: uuid.UUID) -> None:
    await delete_content_reactions_for_targets(
        session=session,
        target_type=ReactionTargetType.POLL,
        target_ids=[poll_id],
    )


async def delete_content_reactions_for_targets(
    *,
    session: AsyncSession,
    target_type: ReactionTargetType,
    target_ids: Iterable[uuid.UUID | int],
) -> None:
    content_ids = [
        _serialize_reaction_target_id(target_id)
        for target_id in dict.fromkeys(target_ids)
    ]
    if not content_ids:
        return
    await session.exec(
        delete(ContentReaction).where(
            col(ContentReaction.content_type) == target_type.value,
            col(ContentReaction.content_id).in_(content_ids),
        )
    )
