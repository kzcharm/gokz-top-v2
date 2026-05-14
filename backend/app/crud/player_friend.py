from collections.abc import Iterable, Sequence
from datetime import datetime

from sqlalchemy import func, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Player, PlayerFriend


async def get_player_friend_steamid64s(
    *,
    session: AsyncSession,
    player_steamid64: int,
) -> set[int]:
    statement = select(PlayerFriend.friend_steamid64).where(
        col(PlayerFriend.player_steamid64) == player_steamid64
    )
    return set((await session.exec(statement)).all())


async def get_player_friends(
    *,
    session: AsyncSession,
    player_steamid64: int,
) -> tuple[list[Player], int]:
    count_statement = select(func.count()).select_from(PlayerFriend).where(
        col(PlayerFriend.player_steamid64) == player_steamid64
    )
    count = int((await session.exec(count_statement)).one())

    statement = (
        select(Player)
        .join(PlayerFriend, Player.steamid64 == PlayerFriend.friend_steamid64)
        .where(col(PlayerFriend.player_steamid64) == player_steamid64)
        .order_by(
            func.lower(func.coalesce(col(Player.alias), col(Player.name))).asc(),
            col(Player.steamid64).asc(),
        )
    )
    players = list((await session.exec(statement)).all())
    return players, count


async def upsert_player_friend_edges(
    *,
    session: AsyncSession,
    edges: Sequence[tuple[int, int, datetime | None]],
) -> None:
    if not edges:
        return

    table = PlayerFriend.__table__  # type: ignore[attr-defined]
    statement = pg_insert(table).values(
        [
            {
                "player_steamid64": player_steamid64,
                "friend_steamid64": friend_steamid64,
                "friend_since": friend_since,
            }
            for player_steamid64, friend_steamid64, friend_since in edges
        ]
    )
    await session.exec(
        statement.on_conflict_do_update(
            index_elements=[table.c.player_steamid64, table.c.friend_steamid64],
            set_={"friend_since": statement.excluded.friend_since},
        )
    )


async def delete_player_friend_edges(
    *,
    session: AsyncSession,
    edges: Iterable[tuple[int, int]],
) -> int:
    edge_list = list(edges)
    if not edge_list:
        return 0

    statement = select(PlayerFriend).where(
        tuple_(
            col(PlayerFriend.player_steamid64),
            col(PlayerFriend.friend_steamid64),
        ).in_(edge_list)
    )
    rows = (await session.exec(statement)).all()
    for row in rows:
        await session.delete(row)
    return len(rows)
