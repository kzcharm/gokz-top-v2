from typing import Any

from sqlalchemy import union
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.crud.ban import not_active_ban_exists_split_clause
from app.crud.player import to_player_ref_public
from app.models import (
    CommunityLeaderboardEntryPublic,
    CommunityLeaderboardListQuery,
    Player,
    PlayerLike,
    PlayerProfileView,
)


def _sort_column(*, query: CommunityLeaderboardListQuery, subquery: Any) -> Any:
    sort_columns = {
        "views_count": subquery.c.views_count,
        "unique_visitors": subquery.c.unique_visitors,
        "likes": subquery.c.likes,
        "unique_likers": subquery.c.unique_likers,
    }
    return sort_columns[query.sort_by]


async def read_community_leaderboard(
    *,
    session: AsyncSession,
    query: CommunityLeaderboardListQuery,
) -> tuple[list[CommunityLeaderboardEntryPublic], int]:
    profile_view_metrics = (
        select(
            col(PlayerProfileView.target_steamid64).label("steamid64"),
            func.count().label("views_count"),
            func.count(func.distinct(PlayerProfileView.viewer_steamid64)).label(
                "unique_visitors"
            ),
        )
        .group_by(col(PlayerProfileView.target_steamid64))
        .subquery()
    )
    like_metrics = (
        select(
            col(PlayerLike.target_steamid64).label("steamid64"),
            func.count().label("likes"),
            func.count(func.distinct(PlayerLike.viewer_steamid64)).label(
                "unique_likers"
            ),
        )
        .group_by(col(PlayerLike.target_steamid64))
        .subquery()
    )
    targets = union(
        select(profile_view_metrics.c.steamid64),
        select(like_metrics.c.steamid64),
    ).subquery()
    all_metrics = (
        select(
            targets.c.steamid64,
            func.coalesce(profile_view_metrics.c.views_count, 0).label(
                "views_count"
            ),
            func.coalesce(profile_view_metrics.c.unique_visitors, 0).label(
                "unique_visitors"
            ),
            func.coalesce(like_metrics.c.likes, 0).label("likes"),
            func.coalesce(like_metrics.c.unique_likers, 0).label("unique_likers"),
        )
        .select_from(targets)
        .outerjoin(
            profile_view_metrics,
            profile_view_metrics.c.steamid64 == targets.c.steamid64,
        )
        .outerjoin(like_metrics, like_metrics.c.steamid64 == targets.c.steamid64)
        .subquery()
    )
    metrics = (
        select(
            all_metrics.c.steamid64,
            all_metrics.c.views_count,
            all_metrics.c.unique_visitors,
            all_metrics.c.likes,
            all_metrics.c.unique_likers,
        )
        .where(
            not_active_ban_exists_split_clause(
                steamid64_column=all_metrics.c.steamid64
            ),
            _sort_column(query=query, subquery=all_metrics) > 0,
        )
        .subquery()
    )

    count = -1
    if query.include_count:
        count = int((await session.exec(select(func.count()).select_from(metrics))).one())

    sort_column = _sort_column(query=query, subquery=metrics)
    page = (
        select(
            metrics.c.steamid64,
            metrics.c.views_count,
            metrics.c.unique_visitors,
            metrics.c.likes,
            metrics.c.unique_likers,
        )
        .order_by(sort_column.desc(), metrics.c.steamid64.asc())
        .offset(query.offset)
        .limit(query.limit)
        .subquery()
    )
    statement = (
        select(Player)
        .select_from(page)
        .add_columns(
            page.c.views_count,
            page.c.unique_visitors,
            page.c.likes,
            page.c.unique_likers,
        )
        .join(Player, col(Player.steamid64) == page.c.steamid64)
        .order_by(_sort_column(query=query, subquery=page).desc(), page.c.steamid64.asc())
    )
    rows = (await session.execute(statement)).all()

    return (
        [
            CommunityLeaderboardEntryPublic(
                rank=query.offset + index,
                player=to_player_ref_public(player=player),
                views_count=int(views_count),
                unique_visitors=int(unique_visitors),
                likes=int(likes),
                unique_likers=int(unique_likers),
            )
            for index, (
                player,
                views_count,
                unique_visitors,
                likes,
                unique_likers,
            ) in enumerate(rows, start=1)
        ],
        count,
    )
