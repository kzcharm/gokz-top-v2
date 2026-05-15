from datetime import datetime

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    Player,
    PlayerProfileHistory,
    PlayerProfileHistoryEntryPublic,
)


async def create_player_profile_history(
    *,
    session: AsyncSession,
    player_steamid64: int,
    name: str | None,
    avatar_hash: str | None,
    changed_at: datetime,
) -> PlayerProfileHistory | None:
    if name is None and avatar_hash is None:
        return None

    history = PlayerProfileHistory(
        player_steamid64=player_steamid64,
        name=name,
        avatar_hash=avatar_hash,
        changed_at=changed_at,
    )
    session.add(history)
    return history


async def create_player_profile_history_if_changed(
    *,
    session: AsyncSession,
    player: Player,
    name: str,
    avatar_hash: str | None,
    changed_at: datetime,
) -> PlayerProfileHistory | None:
    if player.name == name and player.avatar_hash == avatar_hash:
        return None

    return await create_player_profile_history(
        session=session,
        player_steamid64=player.steamid64,
        name=player.name,
        avatar_hash=player.avatar_hash,
        changed_at=changed_at,
    )


async def read_player_profile_history(
    *,
    session: AsyncSession,
    player_steamid64: int,
    offset: int = 0,
    limit: int = 100,
) -> tuple[list[PlayerProfileHistory], int]:
    count_statement = select(func.count()).select_from(PlayerProfileHistory).where(
        col(PlayerProfileHistory.player_steamid64) == player_steamid64
    )
    count = (await session.exec(count_statement)).one()

    statement = (
        select(PlayerProfileHistory)
        .where(col(PlayerProfileHistory.player_steamid64) == player_steamid64)
        .order_by(
            col(PlayerProfileHistory.changed_at).desc(),
            col(PlayerProfileHistory.id).desc(),
        )
        .offset(offset)
        .limit(limit)
    )
    rows = list((await session.exec(statement)).all())
    return rows, count


def to_player_profile_history_public(
    *, history: PlayerProfileHistory
) -> PlayerProfileHistoryEntryPublic:
    return PlayerProfileHistoryEntryPublic(
        id=history.id,
        name=history.name,
        avatar_hash=history.avatar_hash,
        changed_at=history.changed_at,
    )


def to_player_profile_history_publics(
    *, histories: list[PlayerProfileHistory]
) -> list[PlayerProfileHistoryEntryPublic]:
    return [
        to_player_profile_history_public(history=history) for history in histories
    ]
