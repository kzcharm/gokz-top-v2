from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import PlayerHiddenMap


async def list_player_hidden_maps(
    *,
    session: AsyncSession,
    player_steamid64: int,
) -> list[PlayerHiddenMap]:
    statement = (
        select(PlayerHiddenMap)
        .where(col(PlayerHiddenMap.player_steamid64) == player_steamid64)
        .order_by(col(PlayerHiddenMap.created_at).desc(), col(PlayerHiddenMap.id).desc())
    )
    return list((await session.exec(statement)).all())


async def create_player_hidden_map(
    *,
    session: AsyncSession,
    player_steamid64: int,
    map_id: int,
) -> PlayerHiddenMap:
    statement = select(PlayerHiddenMap).where(
        col(PlayerHiddenMap.player_steamid64) == player_steamid64,
        col(PlayerHiddenMap.map_id) == map_id,
    )
    existing = (await session.exec(statement)).first()
    if existing is not None:
        return existing

    hidden_map = PlayerHiddenMap(
        player_steamid64=player_steamid64,
        map_id=map_id,
    )
    session.add(hidden_map)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = (await session.exec(statement)).first()
        if existing is None:
            raise
        return existing

    await session.refresh(hidden_map)
    return hidden_map


async def delete_player_hidden_map(
    *,
    session: AsyncSession,
    player_steamid64: int,
    map_id: int,
) -> bool:
    statement = select(PlayerHiddenMap).where(
        col(PlayerHiddenMap.player_steamid64) == player_steamid64,
        col(PlayerHiddenMap.map_id) == map_id,
    )
    hidden_map = (await session.exec(statement)).first()
    if hidden_map is None:
        return False

    await session.delete(hidden_map)
    await session.commit()
    return True
