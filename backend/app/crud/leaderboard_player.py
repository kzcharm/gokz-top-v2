from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Any, Literal

from sqlalchemy import func, or_
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.regions import get_region_code_for_country, get_region_country_codes
from app.crud.player import to_player_public
from app.crud.record_filter import load_scoped_course_tiers
from app.models import (
    LeaderboardPlayer,
    Map,
    MapCourse,
    Player,
    PlayerLeaderboardEntryPublic,
    PlayerLeaderboardListQuery,
    PlayerLeaderboardRankPublic,
    Record,
    RecordPb,
    RecordScope,
    RecordScopeId,
    scope_mode_ids,
    scope_to_id,
)
from app.models.utils import get_datetime_utc

from .ban import not_active_ban_exists_clause

ELIGIBLE_UNIQUE_MAP_FINISHES = 20
DEFAULT_LOOKBACK = timedelta(hours=24)
WEIGHT_DECAY = Decimal("0.975")


def _scope_from_id(scope_id: int) -> RecordScope:
    return RecordScope[RecordScopeId(scope_id).name]


def _scope_ids_for_mode_id(mode_id: int) -> tuple[int, ...]:
    scope_ids = (
        scope_to_id(RecordScope.OVR),
        scope_to_id(RecordScope.KZT),
        scope_to_id(RecordScope.SKZ),
        scope_to_id(RecordScope.VNL),
    )
    return tuple(
        scope_id for scope_id in scope_ids if mode_id in scope_mode_ids(scope_id)
    )


def _round_rating(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def calculate_weighted_rating(points: Iterable[int]) -> int:
    sorted_points = sorted(points, reverse=True)
    if not sorted_points:
        return 0

    with localcontext() as ctx:
        ctx.prec = 28
        total = Decimal("0")
        multiplier = Decimal("1")
        for point in sorted_points:
            total += Decimal(point) * multiplier
            multiplier *= WEIGHT_DECAY
    return _round_rating(total)


def _not_banned_clause() -> ColumnElement[bool]:
    return not_active_ban_exists_clause(steamid64_column=col(LeaderboardPlayer.steamid64))


def _country_codes_for_geography(
    *,
    country: str | None,
    region: str | None,
) -> tuple[str, ...] | None:
    if country is not None:
        return (country,)
    return get_region_country_codes(region)


def _build_player_leaderboard_entry_public(
    *,
    player: Player,
    rank: int,
    leaderboard_row: LeaderboardPlayer,
) -> PlayerLeaderboardEntryPublic:
    return PlayerLeaderboardEntryPublic(
        rank=rank,
        player=to_player_public(player=player),
        rating=leaderboard_row.rating,
        rating_easy=leaderboard_row.rating_easy,
        rating_hard=leaderboard_row.rating_hard,
        points=leaderboard_row.points,
        wrs_nub=leaderboard_row.wrs_nub,
        wrs_pro=leaderboard_row.wrs_pro,
        records_900_plus=leaderboard_row.records_900_plus,
        records_800_plus=leaderboard_row.records_800_plus,
        unique_map_finishes=leaderboard_row.unique_map_finishes,
    )


async def _load_player_pb_rows(
    *,
    session: AsyncSession,
    scope_id: int,
    steamid64: int,
) -> list[tuple[int, int, bool, int]]:
    return list(
        (
            await session.exec(
                select(
                    col(RecordPb.course_id),
                    col(MapCourse.map_id),
                    col(RecordPb.is_pro_only),
                    col(RecordPb.points),
                )
                .join(MapCourse, col(RecordPb.course_id) == col(MapCourse.id))
                .join(Map, col(MapCourse.map_id) == col(Map.id))
                .where(
                    col(RecordPb.scope) == scope_id,
                    col(RecordPb.steamid64) == steamid64,
                    col(MapCourse.stage) == 0,
                    col(Map.validated).is_(True),
                )
                .order_by(col(RecordPb.course_id).asc(), col(RecordPb.is_pro_only).asc())
            )
        ).all()
    )


def _build_leaderboard_values(
    *,
    rows: Sequence[tuple[int, int, bool, int]],
    tiers_by_course_id: dict[int, int],
) -> dict[str, int]:
    points_by_course_id: dict[int, dict[bool, int]] = defaultdict(dict)
    total_points = 0
    wrs_nub = 0
    wrs_pro = 0
    records_900_plus = 0
    records_800_plus = 0

    for course_id, _map_id, is_pro_only, points in rows:
        total_points += points
        points_by_course_id[course_id][is_pro_only] = points
        if is_pro_only:
            if points == 1000:
                wrs_pro += 1
        elif points == 1000:
            wrs_nub += 1
        if points >= 900:
            records_900_plus += 1
        if points >= 800:
            records_800_plus += 1

    unique_map_finishes = len(points_by_course_id)

    map_best_points: list[int] = []
    easy_points: list[int] = []
    hard_points: list[int] = []
    for course_id, values in points_by_course_id.items():
        best_points = max(values.values())
        map_best_points.append(best_points)
        tier = tiers_by_course_id.get(course_id, 0)
        if 0 < tier <= 4:
            easy_points.append(best_points)
        elif tier >= 5:
            hard_points.append(best_points)

    if unique_map_finishes >= ELIGIBLE_UNIQUE_MAP_FINISHES:
        rating = calculate_weighted_rating(map_best_points)
        rating_easy = calculate_weighted_rating(easy_points)
        rating_hard = calculate_weighted_rating(hard_points)
    else:
        rating = 0
        rating_easy = 0
        rating_hard = 0

    return {
        "rating": rating,
        "rating_easy": rating_easy,
        "rating_hard": rating_hard,
        "points": total_points,
        "wrs_nub": wrs_nub,
        "wrs_pro": wrs_pro,
        "records_900_plus": records_900_plus,
        "records_800_plus": records_800_plus,
        "unique_map_finishes": unique_map_finishes,
    }


async def rebuild_leaderboard_player(
    *,
    session: AsyncSession,
    scope_id: int,
    steamid64: int,
) -> Literal["created", "updated", "deleted", "noop"]:
    rows = await _load_player_pb_rows(
        session=session,
        scope_id=scope_id,
        steamid64=steamid64,
    )
    existing = await session.get(LeaderboardPlayer, (scope_id, steamid64))
    if not rows:
        if existing is None:
            return "noop"
        await session.delete(existing)
        return "deleted"

    scope = _scope_from_id(scope_id)
    course_keys = [(map_id, 0) for _course_id, map_id, _is_pro_only, _points in rows]
    tiers_by_map = await load_scoped_course_tiers(
        session=session,
        course_keys=course_keys,
        scope=scope,
    )
    tiers_by_course_id = {
        course_id: tiers_by_map[(map_id, 0)]
        for course_id, map_id, _is_pro_only, _points in rows
    }
    values = _build_leaderboard_values(rows=rows, tiers_by_course_id=tiers_by_course_id)

    if existing is None:
        session.add(
            LeaderboardPlayer(
                scope=scope_id,
                steamid64=steamid64,
                updated_on=get_datetime_utc(),
                **values,
            )
        )
        return "created"

    current_values = {
        "rating": existing.rating,
        "rating_easy": existing.rating_easy,
        "rating_hard": existing.rating_hard,
        "points": existing.points,
        "wrs_nub": existing.wrs_nub,
        "wrs_pro": existing.wrs_pro,
        "records_900_plus": existing.records_900_plus,
        "records_800_plus": existing.records_800_plus,
        "unique_map_finishes": existing.unique_map_finishes,
    }
    if current_values == values:
        return "noop"

    for field_name, field_value in values.items():
        setattr(existing, field_name, field_value)
    existing.updated_on = get_datetime_utc()
    session.add(existing)
    return "updated"


async def rebuild_leaderboard_players_for_keys(
    *,
    session: AsyncSession,
    keys: Sequence[tuple[int, int]],
) -> tuple[int, int]:
    created = 0
    updated = 0
    for scope_id, steamid64 in keys:
        action = await rebuild_leaderboard_player(
            session=session,
            scope_id=scope_id,
            steamid64=steamid64,
        )
        if action == "created":
            created += 1
        elif action in {"updated", "deleted"}:
            updated += 1
    return created, updated


async def load_leaderboard_player_keys(
    *,
    session: AsyncSession,
    scope_ids: Sequence[int] | None = None,
    steamid64s: Sequence[int] | None = None,
) -> list[tuple[int, int]]:
    source_statement = (
        select(RecordPb.scope, RecordPb.steamid64)
        .join(MapCourse, col(RecordPb.course_id) == col(MapCourse.id))
        .join(Map, col(MapCourse.map_id) == col(Map.id))
        .where(
            col(MapCourse.stage) == 0,
            col(Map.validated).is_(True),
        )
    )
    existing_statement = select(
        col(LeaderboardPlayer.scope), col(LeaderboardPlayer.steamid64)
    )
    if scope_ids:
        source_statement = source_statement.where(col(RecordPb.scope).in_(list(scope_ids)))
        existing_statement = existing_statement.where(
            col(LeaderboardPlayer.scope).in_(list(scope_ids))
        )
    if steamid64s:
        source_statement = source_statement.where(
            col(RecordPb.steamid64).in_(list(steamid64s))
        )
        existing_statement = existing_statement.where(
            col(LeaderboardPlayer.steamid64).in_(list(steamid64s))
        )

    source_keys = set((await session.exec(source_statement.distinct())).all())
    existing_keys = set((await session.exec(existing_statement.distinct())).all())
    return sorted(source_keys | existing_keys)


async def rebuild_leaderboard_players(
    *,
    session: AsyncSession,
    scope_ids: Sequence[int] | None = None,
    steamid64s: Sequence[int] | None = None,
) -> tuple[int, int, int]:
    keys = await load_leaderboard_player_keys(
        session=session,
        scope_ids=scope_ids,
        steamid64s=steamid64s,
    )
    created, updated = await rebuild_leaderboard_players_for_keys(
        session=session,
        keys=keys,
    )
    return len(keys), created, updated


async def load_changed_leaderboard_player_keys(
    *,
    session: AsyncSession,
    window_start: datetime,
) -> list[tuple[int, int]]:
    record_pb_keys = set(
        (
            await session.exec(
                select(RecordPb.scope, RecordPb.steamid64)
                .where(col(RecordPb.updated_on) >= window_start)
                .distinct()
            )
        ).all()
    )

    changed_record_rows = (
        await session.exec(
            select(Record.steamid64, Record.mode_id)
            .where(
                or_(
                    col(Record.created_on) >= window_start,
                    col(Record.updated_on) >= window_start,
                )
            )
            .distinct()
        )
    ).all()
    record_keys = {
        (scope_id, steamid64)
        for steamid64, mode_id in changed_record_rows
        for scope_id in _scope_ids_for_mode_id(mode_id)
    }
    return sorted(record_pb_keys | record_keys)


async def read_player_leaderboard(
    *,
    session: AsyncSession,
    query: PlayerLeaderboardListQuery,
) -> tuple[list[PlayerLeaderboardEntryPublic], int]:
    sort_column = col(getattr(LeaderboardPlayer, query.sort_by))
    sort_expression = sort_column.desc()
    filtered_statement = (
        select(
            col(LeaderboardPlayer.scope).label("scope"),
            col(LeaderboardPlayer.steamid64).label("steamid64"),
            col(LeaderboardPlayer.rating).label("rating"),
            col(LeaderboardPlayer.rating_easy).label("rating_easy"),
            col(LeaderboardPlayer.rating_hard).label("rating_hard"),
            col(LeaderboardPlayer.points).label("points"),
            col(LeaderboardPlayer.wrs_nub).label("wrs_nub"),
            col(LeaderboardPlayer.wrs_pro).label("wrs_pro"),
            col(LeaderboardPlayer.records_900_plus).label("records_900_plus"),
            col(LeaderboardPlayer.records_800_plus).label("records_800_plus"),
            col(LeaderboardPlayer.unique_map_finishes).label("unique_map_finishes"),
        )
        .select_from(LeaderboardPlayer)
        .where(
            col(LeaderboardPlayer.scope) == scope_to_id(query.scope),
            sort_column > 0,
            _not_banned_clause(),
        )
    )
    geography_country_codes = _country_codes_for_geography(
        country=query.country,
        region=query.region,
    )
    if geography_country_codes is not None:
        filtered_statement = filtered_statement.join(
            Player,
            col(Player.steamid64) == col(LeaderboardPlayer.steamid64),
        ).where(col(Player.country).in_(list(geography_country_codes)))

    rank_subquery = (
        filtered_statement.add_columns(
            func.rank().over(order_by=sort_expression).label("rank"),
        ).subquery()
    )

    count = (
        await session.exec(
            select(func.count()).select_from(filtered_statement.subquery())
        )
    ).one()

    statement: Any = (
        select(Player, rank_subquery.c.rank)
        .add_columns(
            rank_subquery.c.rating,
            rank_subquery.c.rating_easy,
            rank_subquery.c.rating_hard,
            rank_subquery.c.points,
            rank_subquery.c.wrs_nub,
            rank_subquery.c.wrs_pro,
            rank_subquery.c.records_900_plus,
            rank_subquery.c.records_800_plus,
            rank_subquery.c.unique_map_finishes,
        )
        .join(Player, col(Player.steamid64) == rank_subquery.c.steamid64)
        .order_by(rank_subquery.c.rank.asc(), rank_subquery.c.steamid64.asc())
        .offset(query.offset)
        .limit(query.limit)
    )
    rows = (await session.exec(statement)).all()

    return (
        [
            _build_player_leaderboard_entry_public(
                player=player,
                rank=rank,
                leaderboard_row=LeaderboardPlayer(
                    scope=scope_to_id(query.scope),
                    steamid64=player.steamid64,
                    rating=rating,
                    rating_easy=rating_easy,
                    rating_hard=rating_hard,
                    points=points,
                    wrs_nub=wrs_nub,
                    wrs_pro=wrs_pro,
                    records_900_plus=records_900_plus,
                    records_800_plus=records_800_plus,
                    unique_map_finishes=unique_map_finishes,
                ),
            )
            for (
                player,
                rank,
                rating,
                rating_easy,
                rating_hard,
                points,
                wrs_nub,
                wrs_pro,
                records_900_plus,
                records_800_plus,
                unique_map_finishes,
            ) in rows
        ],
        count,
    )


async def _read_metric_rank(
    *,
    session: AsyncSession,
    scope: RecordScope,
    steamid64: int,
    metric_name: Literal["points", "rating"],
    metric_value: int,
    country: str | None = None,
    region: str | None = None,
) -> int | None:
    if metric_value <= 0:
        return None

    metric_column = col(getattr(LeaderboardPlayer, metric_name))
    geography_country_codes = _country_codes_for_geography(country=country, region=region)
    higher_count_statement = (
        select(func.count())
        .select_from(LeaderboardPlayer)
        .where(
            col(LeaderboardPlayer.scope) == scope_to_id(scope),
            metric_column > metric_value,
            _not_banned_clause(),
        )
    )
    player_in_scope_statement = (
        select(func.count())
        .select_from(LeaderboardPlayer)
        .where(
            col(LeaderboardPlayer.scope) == scope_to_id(scope),
            col(LeaderboardPlayer.steamid64) == steamid64,
            metric_column > 0,
            _not_banned_clause(),
        )
    )
    if geography_country_codes is not None:
        higher_count_statement = higher_count_statement.join(
            Player,
            col(Player.steamid64) == col(LeaderboardPlayer.steamid64),
        ).where(col(Player.country).in_(list(geography_country_codes)))
        player_in_scope_statement = player_in_scope_statement.join(
            Player,
            col(Player.steamid64) == col(LeaderboardPlayer.steamid64),
        ).where(col(Player.country).in_(list(geography_country_codes)))

    higher_count = (await session.exec(higher_count_statement)).one()
    player_in_scope = (await session.exec(player_in_scope_statement)).one()
    if player_in_scope == 0:
        return None

    return int(higher_count) + 1


async def read_player_leaderboard_rank(
    *,
    session: AsyncSession,
    player: Player,
    scope: RecordScope,
    country: str | None = None,
    region: str | None = None,
) -> PlayerLeaderboardRankPublic:
    leaderboard_row = await session.get(
        LeaderboardPlayer,
        (scope_to_id(scope), player.steamid64),
    )

    rank: int | None = None

    if leaderboard_row is not None:
        rank = await _read_metric_rank(
            session=session,
            scope=scope,
            steamid64=player.steamid64,
            metric_name="rating",
            metric_value=leaderboard_row.rating,
            country=country,
            region=region,
        )
    home_region = get_region_code_for_country(player.country)
    rank_regional: int | None = None
    if leaderboard_row is not None and home_region is not None:
        rank_regional = await _read_metric_rank(
            session=session,
            scope=scope,
            steamid64=player.steamid64,
            metric_name="rating",
            metric_value=leaderboard_row.rating,
            region=home_region,
        )

    return PlayerLeaderboardRankPublic(
        scope=scope,
        rank=rank,
        rank_regional=rank_regional,
        player=to_player_public(player=player),
        rating=leaderboard_row.rating if leaderboard_row is not None else 0,
        rating_easy=leaderboard_row.rating_easy if leaderboard_row is not None else 0,
        rating_hard=leaderboard_row.rating_hard if leaderboard_row is not None else 0,
        points=leaderboard_row.points if leaderboard_row is not None else 0,
        wrs_nub=leaderboard_row.wrs_nub if leaderboard_row is not None else 0,
        wrs_pro=leaderboard_row.wrs_pro if leaderboard_row is not None else 0,
        records_900_plus=leaderboard_row.records_900_plus
        if leaderboard_row is not None
        else 0,
        records_800_plus=leaderboard_row.records_800_plus
        if leaderboard_row is not None
        else 0,
        unique_map_finishes=leaderboard_row.unique_map_finishes
        if leaderboard_row is not None
        else 0,
    )
