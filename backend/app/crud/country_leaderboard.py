from datetime import timedelta

from sqlalchemy import case, func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.crud.ban import not_active_ban_exists_split_clause
from app.crud.player import to_player_ref_public
from app.models import (
    CountryLeaderboardEntryPublic,
    CountryLeaderboardListQuery,
    CountryLeaderboardsPublic,
    LeaderboardPlayer,
    Player,
)
from app.models.utils import get_datetime_utc

MIN_RANKED_PLAYERS = 10
ACTIVE_LOOKBACK = timedelta(days=30)


async def read_country_leaderboard(
    *, session: AsyncSession, query: CountryLeaderboardListQuery
) -> CountryLeaderboardsPublic:
    eligible = (
        select(
            col(LeaderboardPlayer.steamid64).label("steamid64"),
            col(Player.country).label("country"),
            col(Player.last_played_at).label("last_played_at"),
            col(LeaderboardPlayer.rating).label("rating"),
            func.row_number()
            .over(
                partition_by=col(Player.country),
                order_by=(
                    col(LeaderboardPlayer.rating).desc(),
                    col(LeaderboardPlayer.steamid64).asc(),
                ),
            )
            .label("country_rating_rank"),
        )
        .join(Player, col(Player.steamid64) == col(LeaderboardPlayer.steamid64))
        .where(
            col(LeaderboardPlayer.scope) == query.scope,
            col(Player.country).is_not(None),
            col(Player.country) != "",
            not_active_ban_exists_split_clause(
                steamid64_column=col(LeaderboardPlayer.steamid64)
            ),
        )
        .subquery()
    )
    active_cutoff = get_datetime_utc() - ACTIVE_LOOKBACK
    aggregates = (
        select(
            eligible.c.country,
            func.count().label("ranked_players"),
            func.sum(
                case((eligible.c.last_played_at >= active_cutoff, 1), else_=0)
            ).label("active_players"),
            func.percentile_cont(0.5)
            .within_group(eligible.c.rating)
            .label("median_rating"),
            func.avg(eligible.c.rating)
            .filter(eligible.c.country_rating_rank <= 10)
            .label("top10_average_rating"),
        )
        .group_by(eligible.c.country)
        .subquery()
    )
    rows = (
        await session.execute(
            select(aggregates)
            .order_by(
                (aggregates.c.ranked_players >= MIN_RANKED_PLAYERS).desc(),
                aggregates.c.top10_average_rating.desc().nullslast(),
                aggregates.c.median_rating.desc().nullslast(),
                aggregates.c.country.asc().nullslast(),
            )
            .offset(query.offset)
            .limit(query.limit)
        )
    ).all()
    count = int((await session.exec(select(func.count()).select_from(aggregates))).one())

    top_rows = (
        await session.execute(
            select(
                eligible.c.country,
                eligible.c.steamid64,
                eligible.c.country_rating_rank,
            )
            .where(eligible.c.country_rating_rank <= 3)
            .order_by(eligible.c.country, eligible.c.country_rating_rank)
        )
    ).all()
    player_ids = [int(row.steamid64) for row in top_rows]
    players = (
        await session.exec(select(Player).where(col(Player.steamid64).in_(player_ids)))
    ).all() if player_ids else []
    players_by_id = {player.steamid64: player for player in players}
    top_players_by_country: dict[str | None, list[Player]] = {}
    for top_row in top_rows:
        player = players_by_id.get(int(top_row.steamid64))
        if player is not None:
            top_players_by_country.setdefault(top_row.country, []).append(player)

    ranked_position = query.offset
    data: list[CountryLeaderboardEntryPublic] = []
    for row in rows:
        if row.ranked_players >= MIN_RANKED_PLAYERS:
            ranked_position += 1
            rank: int | None = ranked_position
        else:
            rank = None
        data.append(
            CountryLeaderboardEntryPublic(
                rank=rank,
                country=row.country,
                ranked_players=int(row.ranked_players),
                active_players=int(row.active_players or 0),
                top_players=[
                    to_player_ref_public(player=player)
                    for player in top_players_by_country.get(row.country, [])
                ],
                median_rating=float(row.median_rating) if row.median_rating is not None else None,
                top10_average_rating=(
                    float(row.top10_average_rating)
                    if row.top10_average_rating is not None
                    else None
                ),
            )
        )
    return CountryLeaderboardsPublic(data=data, count=count)
