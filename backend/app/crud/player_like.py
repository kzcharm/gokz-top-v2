from datetime import UTC, date, datetime

from sqlalchemy.dialects.postgresql import insert
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import PlayerLike


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
