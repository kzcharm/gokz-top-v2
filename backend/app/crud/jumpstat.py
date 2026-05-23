import uuid
from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import and_
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.crud.ban import not_active_ban_exists_clause
from app.crud.player import to_player_ref_public
from app.models import (
    Jumpstat,
    JumpstatDetailPublic,
    JumpstatLeaderboardEntryPublic,
    JumpstatLeaderboardListQuery,
    JumpstatLeaderboardsPublic,
    JumpstatListQuery,
    JumpstatPublic,
    LeaderboardPlayer,
    Player,
    ServerGroup,
    ServerGroupSummary,
    mode_scope_modes,
)
from app.models.leaderboard_player import min_raw_rating_for_public_rating

type JumpstatRow = tuple[Jumpstat, Player, ServerGroup]


def _to_server_group_summary(*, server_group: ServerGroup) -> ServerGroupSummary:
    return ServerGroupSummary(id=server_group.id, name=server_group.name)


def to_jumpstat_public(
    *,
    jumpstat: Jumpstat,
    player: Player,
    server_group: ServerGroup,
) -> JumpstatPublic:
    return JumpstatPublic.from_row(
        jumpstat=jumpstat,
        player=to_player_ref_public(player=player),
        server_group=_to_server_group_summary(server_group=server_group),
    )


def to_jumpstat_publics(*, rows: Sequence[JumpstatRow]) -> list[JumpstatPublic]:
    return [
        to_jumpstat_public(
            jumpstat=jumpstat,
            player=player,
            server_group=server_group,
        )
        for jumpstat, player, server_group in rows
    ]


def to_jumpstat_detail_public(
    *,
    jumpstat: Jumpstat,
    player: Player,
    server_group: ServerGroup,
) -> JumpstatDetailPublic:
    return JumpstatDetailPublic.from_row(
        jumpstat=jumpstat,
        player=to_player_ref_public(player=player),
        server_group=_to_server_group_summary(server_group=server_group),
    )


def _build_order_by(query: JumpstatListQuery) -> list[ColumnElement[Any]]:
    if query.sort_by == "block":
        block_column = col(Jumpstat.block)
        if query.sort_order == "asc":
            return [
                block_column.asc().nullslast(),
                col(Jumpstat.distance).asc(),
                col(Jumpstat.jumped_at).asc(),
                col(Jumpstat.id).asc(),
            ]
        return [
            block_column.desc().nullslast(),
            col(Jumpstat.distance).desc(),
            col(Jumpstat.jumped_at).desc(),
            col(Jumpstat.id).desc(),
        ]

    sort_column_map = {
        "distance": col(Jumpstat.distance),
        "jumped_at": col(Jumpstat.jumped_at),
        "created_at": col(Jumpstat.created_at),
    }
    sort_column = sort_column_map[query.sort_by]
    if query.sort_order == "asc":
        return [sort_column.asc(), col(Jumpstat.id).asc()]
    return [sort_column.desc(), col(Jumpstat.id).desc()]


def to_jumpstat_leaderboard_publics(
    *,
    rows: Sequence[JumpstatRow],
    offset: int,
) -> list[JumpstatLeaderboardEntryPublic]:
    return [
        JumpstatLeaderboardEntryPublic.from_row(
            rank=offset + index,
            jumpstat=jumpstat,
            player=to_player_ref_public(player=player),
            server_group=_to_server_group_summary(server_group=server_group),
        )
        for index, (jumpstat, player, server_group) in enumerate(rows, start=1)
    ]


def _leaderboard_base_order_by(columns: Any) -> list[Any]:
    return [
        columns.distance.desc(),
        columns.jumped_at.desc(),
        columns.id.desc(),
    ]


def _leaderboard_order_by(
    *,
    query: JumpstatLeaderboardListQuery,
    columns: Any,
) -> list[Any]:
    if query.sort_by == "block":
        return [
            columns.block.desc().nullslast(),
            columns.distance.desc(),
            columns.jumped_at.desc(),
            columns.id.desc(),
        ]
    return _leaderboard_base_order_by(columns)


async def read_jumpstat_leaderboard(
    *,
    session: AsyncSession,
    query: JumpstatLeaderboardListQuery,
) -> JumpstatLeaderboardsPublic:
    minimum_raw_rating = min_raw_rating_for_public_rating(query.min_rating)
    ranked_jumpstats_subquery = (
        select(
            col(Jumpstat.id).label("id"),
            col(Jumpstat.distance).label("distance"),
            col(Jumpstat.block).label("block"),
            col(Jumpstat.jumped_at).label("jumped_at"),
            func.row_number()
            .over(
                partition_by=col(Jumpstat.player_steamid64),
                order_by=_leaderboard_base_order_by(Jumpstat),
            )
            .label("pb_rank"),
        )
        .select_from(Jumpstat)
        .join(
            LeaderboardPlayer,
            and_(
                col(LeaderboardPlayer.steamid64) == col(Jumpstat.player_steamid64),
                col(LeaderboardPlayer.scope) == query.scope,
            ),
        )
        .where(
            col(Jumpstat.type) == query.type,
            col(Jumpstat.mode).in_(list(mode_scope_modes(query.scope))),
            not_active_ban_exists_clause(
                steamid64_column=Jumpstat.__table__.c.player_steamid64
            ),
            col(LeaderboardPlayer.rating) >= minimum_raw_rating,
        )
        .subquery()
    )
    pb_jumpstats_subquery = (
        select(
            ranked_jumpstats_subquery.c.id,
            ranked_jumpstats_subquery.c.distance,
            ranked_jumpstats_subquery.c.block,
            ranked_jumpstats_subquery.c.jumped_at,
        )
        .where(ranked_jumpstats_subquery.c.pb_rank == 1)
        .subquery()
    )
    page_subquery = (
        select(
            pb_jumpstats_subquery.c.id,
            pb_jumpstats_subquery.c.distance,
            pb_jumpstats_subquery.c.block,
            pb_jumpstats_subquery.c.jumped_at,
        )
        .order_by(*_leaderboard_order_by(query=query, columns=pb_jumpstats_subquery.c))
        .offset(query.offset)
        .limit(query.limit)
        .subquery()
    )

    rows = cast(
        list[JumpstatRow],
        list(
            (
                await session.exec(
                    select(Jumpstat, Player, ServerGroup)
                    .select_from(page_subquery)
                    .join(Jumpstat, col(Jumpstat.id) == page_subquery.c.id)
                    .join(Player, col(Player.steamid64) == col(Jumpstat.player_steamid64))
                    .join(ServerGroup, col(ServerGroup.id) == col(Jumpstat.server_group_id))
                    .order_by(*_leaderboard_order_by(query=query, columns=page_subquery.c))
                )
            ).all()
        ),
    )
    count = int(
        (
            await session.exec(
                select(func.count()).select_from(pb_jumpstats_subquery)
            )
        ).one()
    )
    return JumpstatLeaderboardsPublic(
        data=to_jumpstat_leaderboard_publics(rows=rows, offset=query.offset),
        count=count,
    )


async def read_jumpstats(
    *,
    session: AsyncSession,
    query: JumpstatListQuery,
    player_steamid64: int | None = None,
) -> tuple[list[JumpstatRow], int]:
    filters: list[ColumnElement[bool]] = []

    if player_steamid64 is not None:
        filters.append(col(Jumpstat.player_steamid64) == player_steamid64)
    if query.type is not None:
        filters.append(col(Jumpstat.type) == query.type)
    if query.mode is not None:
        filters.append(col(Jumpstat.mode) == query.mode)
    if query.block is not None:
        filters.append(col(Jumpstat.block) == query.block)
    if query.server_group_id is not None:
        filters.append(col(Jumpstat.server_group_id) == query.server_group_id)
    if query.exclude_cheaters:
        filters.append(
            not_active_ban_exists_clause(
                steamid64_column=Jumpstat.__table__.c.player_steamid64
            )
        )

    count_statement = select(func.count()).select_from(Jumpstat)
    statement = (
        select(Jumpstat, Player, ServerGroup)
        .select_from(Jumpstat)
        .join(Player, col(Player.steamid64) == col(Jumpstat.player_steamid64))
        .join(ServerGroup, col(ServerGroup.id) == col(Jumpstat.server_group_id))
    )
    for condition in filters:
        count_statement = count_statement.where(condition)
        statement = statement.where(condition)

    rows = cast(
        list[JumpstatRow],
        list(
            (
                await session.exec(
                    statement.order_by(*_build_order_by(query))
                    .offset(query.offset)
                    .limit(query.limit)
                )
            ).all()
        ),
    )
    count = int((await session.exec(count_statement)).one())
    return rows, count


async def get_jumpstat_by_id(
    *,
    session: AsyncSession,
    jumpstat_id: uuid.UUID,
) -> JumpstatRow | None:
    statement = (
        select(Jumpstat, Player, ServerGroup)
        .select_from(Jumpstat)
        .join(Player, col(Player.steamid64) == col(Jumpstat.player_steamid64))
        .join(ServerGroup, col(ServerGroup.id) == col(Jumpstat.server_group_id))
        .where(col(Jumpstat.id) == jumpstat_id)
    )
    return (await session.exec(statement)).first()
