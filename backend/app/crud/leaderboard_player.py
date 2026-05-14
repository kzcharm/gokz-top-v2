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

from app.core.rank_system import get_rank_system_settings
from app.core.regions import get_region_code_for_country, get_region_country_codes
from app.crud.player import to_player_ref_public
from app.crud.record_filter import load_scoped_course_tiers
from app.models import (
    Ban,
    LeaderboardPlayer,
    LeaderboardPlayerCount,
    Map,
    MapCourse,
    ModeScope,
    Player,
    PlayerLeaderboardEntryPublic,
    PlayerLeaderboardListQuery,
    PlayerLeaderboardRankPublic,
    Record,
    RecordPb,
    legacy_mode_id_to_kz_mode,
    mode_scope_from_id,
    mode_scope_modes,
    mode_scope_to_id,
)
from app.models.leaderboard_player import LeaderboardPlayerSortBy
from app.models.utils import get_datetime_utc

from .ban import not_active_ban_exists_split_clause

ELIGIBLE_UNIQUE_MAP_FINISHES = 10
DEFAULT_LOOKBACK = timedelta(hours=24)


async def load_player_ratings_by_scope(
    *,
    session: AsyncSession,
    steamid64s: Sequence[int],
) -> dict[int, dict[ModeScope, int]]:
    unique_steamid64s = tuple(dict.fromkeys(steamid64s))
    if not unique_steamid64s:
        return {}

    rows = (
        await session.exec(
            select(
                LeaderboardPlayer.steamid64,
                LeaderboardPlayer.scope,
                LeaderboardPlayer.rating,
            ).where(col(LeaderboardPlayer.steamid64).in_(unique_steamid64s))
        )
    ).all()
    ratings_by_player: dict[int, dict[ModeScope, int]] = defaultdict(dict)
    for steamid64, scope, rating in rows:
        ratings_by_player[int(steamid64)][scope] = rating
    return dict(ratings_by_player)

def _scope_ids_for_mode_id(mode_id: int) -> tuple[int, ...]:
    return tuple(
        mode_scope_to_id(scope)
        for scope in ModeScope
        if legacy_mode_id_to_kz_mode(mode_id) in mode_scope_modes(scope)
    )


def _round_rating(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def calculate_weighted_rating(points: Iterable[int]) -> int:
    sorted_points = sorted(points, reverse=True)
    if not sorted_points:
        return 0
    settings = get_rank_system_settings().rating

    with localcontext() as ctx:
        ctx.prec = 28
        total = Decimal("0")
        multiplier = Decimal("1")
        for point in sorted_points:
            total += Decimal(point) * multiplier
            multiplier *= settings.decay
        total *= settings.multiplier
    return _round_rating(total)


def _not_banned_clause() -> ColumnElement[bool]:
    return not_active_ban_exists_split_clause(
        steamid64_column=col(LeaderboardPlayer.steamid64)
    )


async def _player_has_active_ban(
    *,
    session: AsyncSession,
    steamid64: int,
) -> bool:
    return bool(
        (
            await session.exec(
                select(func.count())
                .select_from(Ban)
                .where(
                    col(Ban.steamid64) == steamid64,
                    or_(
                        col(Ban.expires_on).is_(None),
                        col(Ban.expires_on) >= get_datetime_utc(),
                    ),
                )
            )
        ).one()
    )


def _country_codes_for_geography(
    *,
    country: str | None,
    region: str | None,
) -> tuple[str, ...] | None:
    if country is not None:
        return (country,)
    return get_region_country_codes(region)


def _leaderboard_order_expressions(
    *,
    sort_by: LeaderboardPlayerSortBy,
    columns: Any,
) -> tuple[Any, ...]:
    primary_expression = getattr(columns, sort_by).desc()
    if sort_by == "rating":
        return (
            primary_expression,
            columns.steamid64.asc(),
        )
    return (
        primary_expression,
        columns.rating.desc(),
        columns.steamid64.asc(),
    )


async def _read_cached_scope_count(
    *,
    session: AsyncSession,
    scope: ModeScope,
) -> int | None:
    cached_count = await session.get(LeaderboardPlayerCount, scope)
    if cached_count is None:
        return None
    return cached_count.total


async def _count_active_banned_scope_players(
    *,
    session: AsyncSession,
    scope: ModeScope,
) -> int:
    active_banned_players = (
        select(col(Ban.steamid64).label("steamid64"))
        .where(
            or_(
                col(Ban.expires_on).is_(None),
                col(Ban.expires_on) >= get_datetime_utc(),
            )
        )
        .distinct()
        .subquery()
    )
    return int(
        (
            await session.exec(
                select(func.count())
                .select_from(LeaderboardPlayer)
                .join(
                    active_banned_players,
                    active_banned_players.c.steamid64 == col(LeaderboardPlayer.steamid64),
                )
                .where(col(LeaderboardPlayer.scope) == scope)
            )
        ).one()
    )


async def rebuild_leaderboard_player_count(
    *,
    session: AsyncSession,
    scope: ModeScope,
) -> Literal["created", "updated", "noop"]:
    total = int(
        (
            await session.exec(
                select(func.count())
                .select_from(LeaderboardPlayer)
                .where(col(LeaderboardPlayer.scope) == scope)
            )
        ).one()
    )
    cached_count = await session.get(LeaderboardPlayerCount, scope)
    if cached_count is None:
        session.add(
            LeaderboardPlayerCount(
                scope=scope,
                total=total,
                updated_at=get_datetime_utc(),
            )
        )
        return "created"
    if cached_count.total == total:
        return "noop"
    cached_count.total = total
    cached_count.updated_at = get_datetime_utc()
    session.add(cached_count)
    return "updated"


async def rebuild_leaderboard_player_counts(
    *,
    session: AsyncSession,
    scope_ids: Sequence[int],
) -> tuple[int, int]:
    created = 0
    updated = 0
    for scope_id in sorted(set(scope_ids)):
        action = await rebuild_leaderboard_player_count(
            session=session,
            scope=mode_scope_from_id(scope_id),
        )
        if action == "created":
            created += 1
        elif action == "updated":
            updated += 1
    return created, updated


def _build_player_leaderboard_entry_public(
    *,
    player: Player,
    rank: int,
    leaderboard_row: LeaderboardPlayer,
) -> PlayerLeaderboardEntryPublic:
    return PlayerLeaderboardEntryPublic(
        rank=rank,
        player=to_player_ref_public(player=player),
        rating=leaderboard_row.rating,
        raw_rating=leaderboard_row.rating,
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
                    col(RecordPb.scope) == mode_scope_from_id(scope_id),
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

    for course_id, _map_id, is_pro_only, points in rows:
        total_points += points
        points_by_course_id[course_id][is_pro_only] = points
        if is_pro_only:
            if points == 1000:
                wrs_pro += 1
        elif points == 1000:
            wrs_nub += 1

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

    records_900_plus = sum(1 for best_points in map_best_points if best_points >= 900)
    records_800_plus = sum(1 for best_points in map_best_points if best_points >= 800)

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
    scope = mode_scope_from_id(scope_id)
    existing = await session.get(LeaderboardPlayer, (scope, steamid64))
    if await _player_has_active_ban(session=session, steamid64=steamid64):
        if existing is None:
            return "noop"
        await session.delete(existing)
        return "deleted"

    rows = await _load_player_pb_rows(
        session=session,
        scope_id=scope_id,
        steamid64=steamid64,
    )
    if not rows:
        if existing is None:
            return "noop"
        await session.delete(existing)
        return "deleted"

    if len({course_id for course_id, _map_id, _is_pro_only, _points in rows}) < (
        ELIGIBLE_UNIQUE_MAP_FINISHES
    ):
        if existing is None:
            return "noop"
        await session.delete(existing)
        return "deleted"

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
                scope=scope,
                steamid64=steamid64,
                updated_at=get_datetime_utc(),
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
    existing.updated_at = get_datetime_utc()
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
    await rebuild_leaderboard_player_counts(
        session=session,
        scope_ids=[scope_id for scope_id, _steamid64 in keys],
    )
    return created, updated


async def load_leaderboard_player_keys(
    *,
    session: AsyncSession,
    scope_ids: Sequence[int] | None = None,
    steamid64s: Sequence[int] | None = None,
    prioritize_existing_rating: bool = False,
) -> list[tuple[int, int]]:
    source_statement = (
        select(RecordPb.scope, RecordPb.steamid64)
        .join(MapCourse, col(RecordPb.course_id) == col(MapCourse.id))
        .join(Map, col(MapCourse.map_id) == col(Map.id))
        .where(
            col(MapCourse.stage) == 0,
            col(Map.validated).is_(True),
            not_active_ban_exists_split_clause(
                steamid64_column=col(RecordPb.steamid64)
            ),
        )
        .group_by(col(RecordPb.scope), col(RecordPb.steamid64))
        .having(
            func.count(func.distinct(col(RecordPb.course_id)))
            >= ELIGIBLE_UNIQUE_MAP_FINISHES
        )
    )
    existing_statement = select(
        col(LeaderboardPlayer.scope), col(LeaderboardPlayer.steamid64)
    )
    if scope_ids:
        source_statement = source_statement.where(
            col(RecordPb.scope).in_([mode_scope_from_id(scope_id) for scope_id in scope_ids])
        )
        existing_statement = existing_statement.where(
            col(LeaderboardPlayer.scope).in_(
                [mode_scope_from_id(scope_id) for scope_id in scope_ids]
            )
        )
    if steamid64s:
        source_statement = source_statement.where(
            col(RecordPb.steamid64).in_(list(steamid64s))
        )
        existing_statement = existing_statement.where(
            col(LeaderboardPlayer.steamid64).in_(list(steamid64s))
        )

    source_keys = {
        (mode_scope_to_id(scope), steamid64)
        for scope, steamid64 in (await session.exec(source_statement.distinct())).all()
    }
    existing_keys = {
        (mode_scope_to_id(scope), steamid64)
        for scope, steamid64 in (await session.exec(existing_statement.distinct())).all()
    }
    if not prioritize_existing_rating:
        return sorted(source_keys | existing_keys)

    prioritized_existing_statement = select(
        col(LeaderboardPlayer.scope), col(LeaderboardPlayer.steamid64)
    )
    if scope_ids:
        prioritized_existing_statement = prioritized_existing_statement.where(
            col(LeaderboardPlayer.scope).in_(
                [mode_scope_from_id(scope_id) for scope_id in scope_ids]
            )
        )
    if steamid64s:
        prioritized_existing_statement = prioritized_existing_statement.where(
            col(LeaderboardPlayer.steamid64).in_(list(steamid64s))
        )
    prioritized_existing_statement = prioritized_existing_statement.order_by(
        col(LeaderboardPlayer.scope).asc(),
        col(LeaderboardPlayer.rating).desc(),
        col(LeaderboardPlayer.steamid64).asc(),
    )
    existing_keys_in_order = [
        (mode_scope_to_id(scope), steamid64)
        for scope, steamid64 in (await session.exec(prioritized_existing_statement)).all()
    ]
    remaining_source_keys = sorted(source_keys - set(existing_keys_in_order))
    return [*existing_keys_in_order, *remaining_source_keys]


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
    if scope_ids:
        await rebuild_leaderboard_player_counts(
            session=session,
            scope_ids=scope_ids,
        )
    return len(keys), created, updated


async def load_changed_leaderboard_player_keys(
    *,
    session: AsyncSession,
    window_start: datetime,
) -> list[tuple[int, int]]:
    record_pb_keys = {
        (mode_scope_to_id(scope), steamid64)
        for scope, steamid64 in (
            await session.exec(
                select(RecordPb.scope, RecordPb.steamid64)
                .where(col(RecordPb.updated_at) >= window_start)
                .distinct()
            )
        ).all()
    }

    changed_record_rows = (
        await session.exec(
            select(Record.steamid64, Record.mode)
            .where(
                or_(
                    col(Record.created_at) >= window_start,
                    col(Record.updated_at) >= window_start,
                )
            )
            .distinct()
        )
    ).all()
    record_keys = {
        (scope_id, steamid64)
        for steamid64, mode in changed_record_rows
        for scope_id in _scope_ids_for_mode_id(mode.mode_id)
    }
    return sorted(record_pb_keys | record_keys)


async def read_player_leaderboard(
    *,
    session: AsyncSession,
    query: PlayerLeaderboardListQuery,
) -> tuple[list[PlayerLeaderboardEntryPublic], int]:
    base_order_expressions = _leaderboard_order_expressions(
        sort_by=query.sort_by,
        columns=LeaderboardPlayer,
    )
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
            col(LeaderboardPlayer.scope) == query.scope,
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

    page_subquery = (
        filtered_statement.order_by(*base_order_expressions)
        .offset(query.offset)
        .limit(query.limit)
        .subquery()
    )
    page_order_expressions = _leaderboard_order_expressions(
        sort_by=query.sort_by,
        columns=page_subquery.c,
    )

    count = -1
    if query.include_count:
        scope = query.scope
        if geography_country_codes is None:
            cached_total = await _read_cached_scope_count(
                session=session,
                scope=scope,
            )
            if cached_total is not None:
                count = max(
                    cached_total
                    - await _count_active_banned_scope_players(
                        session=session,
                        scope=scope,
                    ),
                    0,
                )
            else:
                count = int(
                    (
                        await session.exec(
                            select(func.count())
                            .select_from(LeaderboardPlayer)
                            .where(
                                col(LeaderboardPlayer.scope) == scope,
                                _not_banned_clause(),
                            )
                        )
                    ).one()
                )
        else:
            count = int(
                (
                    await session.exec(
                        select(func.count())
                        .select_from(LeaderboardPlayer)
                        .join(
                            Player,
                            col(Player.steamid64) == col(LeaderboardPlayer.steamid64),
                        )
                        .where(
                            col(LeaderboardPlayer.scope) == scope,
                            _not_banned_clause(),
                            col(Player.country).in_(list(geography_country_codes)),
                        )
                    )
                ).one()
            )

    statement: Any = (
        select(Player)
        .select_from(page_subquery)
        .add_columns(
            page_subquery.c.rating,
            page_subquery.c.rating_easy,
            page_subquery.c.rating_hard,
            page_subquery.c.points,
            page_subquery.c.wrs_nub,
            page_subquery.c.wrs_pro,
            page_subquery.c.records_900_plus,
            page_subquery.c.records_800_plus,
            page_subquery.c.unique_map_finishes,
        )
        .join(Player, col(Player.steamid64) == page_subquery.c.steamid64)
        .order_by(*page_order_expressions)
    )
    rows = (await session.execute(statement)).all()

    return (
        [
            _build_player_leaderboard_entry_public(
                player=player,
                rank=query.offset + index,
                leaderboard_row=LeaderboardPlayer(
                    scope=query.scope,
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
            for index, (
                player,
                rating,
                rating_easy,
                rating_hard,
                points,
                wrs_nub,
                wrs_pro,
                records_900_plus,
                records_800_plus,
                unique_map_finishes,
            ) in enumerate(rows, start=1)
        ],
        count,
    )


async def _read_metric_rank(
    *,
    session: AsyncSession,
    scope: ModeScope,
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
            col(LeaderboardPlayer.scope) == scope,
            metric_column > metric_value,
            _not_banned_clause(),
        )
    )
    player_in_scope_statement = (
        select(func.count())
        .select_from(LeaderboardPlayer)
        .where(
            col(LeaderboardPlayer.scope) == scope,
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
    scope: ModeScope,
    country: str | None = None,
    region: str | None = None,
) -> PlayerLeaderboardRankPublic:
    leaderboard_row = await session.get(
        LeaderboardPlayer,
        (scope, player.steamid64),
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
        region=home_region,
        player=to_player_ref_public(player=player),
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
