from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Any, Literal

from sqlalchemy import func, or_, true
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.crud.player import to_player_public
from app.crud.record_filter import load_scoped_course_tiers
from app.models import (
    LeaderboardPlayer,
    Map,
    MapCourse,
    Player,
    PlayerLeaderboardEntryPublic,
    PlayerLeaderboardListQuery,
    Record,
    RecordPb,
    RecordScope,
    RecordScopeId,
    scope_mode_ids,
    scope_to_id,
)
from app.models.utils import get_datetime_utc

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
    return true()


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
    sort_expression = (
        sort_column.asc() if query.sort_order == "asc" else sort_column.desc()
    )
    rank_subquery = (
        select(
            LeaderboardPlayer,
            func.rank()
            .over(order_by=sort_expression)
            .label("rank"),
        )
        .where(
            col(LeaderboardPlayer.scope) == scope_to_id(query.scope),
            sort_column > 0,
            _not_banned_clause(),
        )
        .subquery()
    )

    count = (
        await session.exec(
            select(func.count())
            .select_from(LeaderboardPlayer)
            .where(
                col(LeaderboardPlayer.scope) == scope_to_id(query.scope),
                sort_column > 0,
                _not_banned_clause(),
            )
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
            PlayerLeaderboardEntryPublic(
                rank=rank,
                player=to_player_public(player=player),
                rating=rating,
                rating_easy=rating_easy,
                rating_hard=rating_hard,
                points=points,
                wrs_nub=wrs_nub,
                wrs_pro=wrs_pro,
                records_900_plus=records_900_plus,
                records_800_plus=records_800_plus,
                unique_map_finishes=unique_map_finishes,
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
