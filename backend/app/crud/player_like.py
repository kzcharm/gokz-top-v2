from datetime import UTC, date, datetime

from sqlalchemy.dialects.postgresql import insert
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Player, PlayerLike


def get_utc_today(*, now: datetime | None = None) -> date:
    reference = now or datetime.now(UTC)
    normalized = (
        reference.astimezone(UTC) if reference.tzinfo else reference.replace(tzinfo=UTC)
    )
    return normalized.date()


async def count_player_likes(
    *,
    session: AsyncSession,
    target_steamid64: int,
) -> int:
    statement = select(func.count()).select_from(PlayerLike).where(
        PlayerLike.target_steamid64 == target_steamid64
    )
    return int((await session.exec(statement)).one())


async def get_player_likers(
    *,
    session: AsyncSession,
    target_steamid64: int,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[Player], int]:
    latest_like_subquery = (
        select(
            PlayerLike.viewer_steamid64,
            func.max(PlayerLike.created_at).label("latest_like_at"),
        )
        .where(PlayerLike.target_steamid64 == target_steamid64)
        .group_by(PlayerLike.viewer_steamid64)
        .subquery()
    )
    count_statement = select(func.count()).select_from(latest_like_subquery)
    count = int((await session.exec(count_statement)).one())
    statement = (
        select(Player)
        .join(
            latest_like_subquery,
            col(Player.steamid64) == latest_like_subquery.c.viewer_steamid64,
        )
        .order_by(
            latest_like_subquery.c.latest_like_at.desc(),
            col(Player.steamid64).desc(),
        )
        .offset(offset)
        .limit(limit)
    )
    likers = list((await session.exec(statement)).all())
    return likers, count


async def create_player_like(
    *,
    session: AsyncSession,
    viewer_steamid64: int,
    target_steamid64: int,
    now: datetime | None = None,
) -> bool:
    if viewer_steamid64 == target_steamid64:
        return False

    created_at = now or datetime.now(UTC)
    like_date = get_utc_today(now=created_at)
    statement = (
        insert(PlayerLike)
        .values(
            viewer_steamid64=viewer_steamid64,
            target_steamid64=target_steamid64,
            like_date=like_date,
            created_at=created_at,
        )
        .on_conflict_do_nothing(
            index_elements=[
                PlayerLike.viewer_steamid64,
                PlayerLike.target_steamid64,
                PlayerLike.like_date,
            ]
        )
        .returning(PlayerLike.viewer_steamid64)
    )
    result = await session.exec(statement)
    await session.commit()
    return result.one_or_none() is not None
