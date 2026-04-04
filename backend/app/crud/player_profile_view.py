from datetime import UTC, date, datetime

from sqlalchemy.dialects.postgresql import insert
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import PlayerProfileView


def get_utc_today(*, now: datetime | None = None) -> date:
    reference = now or datetime.now(UTC)
    normalized = (
        reference.astimezone(UTC) if reference.tzinfo else reference.replace(tzinfo=UTC)
    )
    return normalized.date()


async def count_player_profile_views(
    *,
    session: AsyncSession,
    target_steamid64: int,
) -> int:
    statement = select(func.count()).select_from(PlayerProfileView).where(
        PlayerProfileView.target_steamid64 == target_steamid64
    )
    return int((await session.exec(statement)).one())


async def create_player_profile_view(
    *,
    session: AsyncSession,
    viewer_steamid64: int,
    target_steamid64: int,
    now: datetime | None = None,
) -> None:
    if viewer_steamid64 == target_steamid64:
        return

    created_at = now or datetime.now(UTC)
    view_date = get_utc_today(now=created_at)
    statement = (
        insert(PlayerProfileView)
        .values(
            viewer_steamid64=viewer_steamid64,
            target_steamid64=target_steamid64,
            view_date=view_date,
            created_at=created_at,
        )
        .on_conflict_do_nothing(
            index_elements=[
                PlayerProfileView.viewer_steamid64,
                PlayerProfileView.target_steamid64,
                PlayerProfileView.view_date,
            ]
        )
    )
    await session.exec(statement)
    await session.commit()
