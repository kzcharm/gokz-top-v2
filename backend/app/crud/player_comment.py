import uuid

from sqlalchemy import func
from sqlalchemy.orm import aliased
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.crud.player import to_player_ref_public
from app.models import Player, PlayerComment, PlayerCommentPublic


def _player_comment_order_by() -> tuple:
    return (
        col(PlayerComment.created_at).desc(),
        col(PlayerComment.id).desc(),
    )


def to_player_comment_public(
    *,
    comment: PlayerComment,
    author: Player,
) -> PlayerCommentPublic:
    return PlayerCommentPublic(
        id=comment.id,
        text=comment.text,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
        author=to_player_ref_public(player=author),
    )


async def create_player_comment(
    *,
    session: AsyncSession,
    author_steamid64: int,
    target_steamid64: int,
    text: str,
) -> PlayerComment:
    comment = PlayerComment(
        author_steamid64=author_steamid64,
        target_steamid64=target_steamid64,
        text=text,
    )
    session.add(comment)
    await session.commit()
    await session.refresh(comment)
    return comment


async def get_player_comment(
    *,
    session: AsyncSession,
    id: uuid.UUID,
) -> PlayerComment | None:
    return await session.get(PlayerComment, id)


async def read_player_comments(
    *,
    session: AsyncSession,
    target_steamid64: int,
    offset: int,
    limit: int,
) -> tuple[list[tuple[PlayerComment, Player]], int]:
    author_player = aliased(Player)
    count_statement = select(func.count()).select_from(PlayerComment).where(
        col(PlayerComment.target_steamid64) == target_steamid64
    )
    count = int((await session.exec(count_statement)).one())

    statement = (
        select(PlayerComment, author_player)
        .join(
            author_player,
            col(author_player.steamid64) == col(PlayerComment.author_steamid64),
        )
        .where(col(PlayerComment.target_steamid64) == target_steamid64)
        .order_by(*_player_comment_order_by())
        .offset(offset)
        .limit(limit)
    )
    rows = list((await session.exec(statement)).all())
    return rows, count


async def delete_player_comment(
    *,
    session: AsyncSession,
    comment: PlayerComment,
) -> None:
    await session.delete(comment)
    await session.commit()
