from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import datetime

from sqlalchemy import case, delete, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    Map,
    MapLeaderboardCache,
    MapLeaderboardEntryPublic,
    MapLeaderboardsPublic,
    MapRefPublic,
    ModeScope,
    ModeScopeId,
    Record,
    get_datetime_utc,
)
from app.models.record import MODE_SCOPE_MODE_IDS, mode_scope_to_id

from .ban import not_active_ban_exists_clause
from .map_review import load_map_review_summaries
from .record_filter import load_map_tiers_by_scope


def _normalize_scope_list(scopes: Iterable[ModeScope] | None) -> list[ModeScope]:
    if scopes is None:
        return list(ModeScope)
    return list(dict.fromkeys(scopes))


def _scope_ids_for_mode_id(mode_id: int) -> tuple[int, ...]:
    return tuple(
        scope_id
        for scope_id, mode_ids in MODE_SCOPE_MODE_IDS.items()
        if mode_id in mode_ids
    )


async def _load_map_leaderboard_cache_rows(
    *,
    session: AsyncSession,
    scope: ModeScope,
    map_ids: Sequence[int],
) -> dict[int, MapLeaderboardCache]:
    unique_map_ids = list(dict.fromkeys(map_ids))
    if not unique_map_ids:
        return {}

    rows = (
        await session.exec(
            select(MapLeaderboardCache).where(
                col(MapLeaderboardCache.scope) == scope,
                col(MapLeaderboardCache.map_id).in_(unique_map_ids),
            )
        )
    ).all()
    return {row.map_id: row for row in rows}


async def _load_target_map_ids(
    *,
    session: AsyncSession,
    map_ids: Sequence[int] | None,
) -> list[int]:
    if map_ids is not None:
        return list(dict.fromkeys(map_ids))

    rows = (await session.exec(select(Map.id).order_by(col(Map.id).asc()))).all()
    return [map_id for map_id in rows]


async def _build_map_leaderboard_values_for_scope(
    *,
    session: AsyncSession,
    scope: ModeScope,
    map_ids: Sequence[int] | None,
) -> list[dict[str, object]]:
    now = get_datetime_utc()
    record_filters = [
        col(Record.stage) == 0,
        col(Record.is_valid).is_(True),
        col(Record.mode_id).in_(list(MODE_SCOPE_MODE_IDS[mode_scope_to_id(scope)])),
        not_active_ban_exists_clause(steamid64_column=col(Record.steamid64)),
    ]
    if map_ids is not None:
        record_filters.append(col(Record.map_id).in_(list(map_ids)))

    per_player = (
        select(
            Record.map_id.label("map_id"),
            Record.steamid64.label("steamid64"),
            func.count().label("player_finishes"),
            func.coalesce(func.sum(Record.time), 0).label("player_playtime"),
            func.min(Record.time).label("first_completion_time"),
            func.bool_or(col(Record.teleports) == 0).label("has_pro_finish"),
        )
        .select_from(Record)
        .where(*record_filters)
        .group_by(Record.map_id, Record.steamid64)
        .subquery()
    )

    statement = (
        select(
            per_player.c.map_id,
            func.count().label("unique_nub_finishes"),
            func.coalesce(func.sum(per_player.c.player_finishes), 0).label("total_finishes"),
            func.coalesce(func.sum(per_player.c.player_playtime), 0).label("total_playtime"),
            func.avg(per_player.c.first_completion_time).label(
                "average_first_completion_time"
            ),
            func.percentile_cont(0.5).within_group(
                per_player.c.first_completion_time
            ).label("median_first_completion_time"),
            func.avg(per_player.c.player_playtime).label("average_playtime_per_player"),
            func.percentile_cont(0.5).within_group(per_player.c.player_playtime).label(
                "median_playtime_per_player"
            ),
            func.avg(per_player.c.player_finishes).label("average_finishes_per_player"),
            func.percentile_cont(0.5).within_group(per_player.c.player_finishes).label(
                "median_finishes_per_player"
            ),
            func.coalesce(
                func.sum(
                    case((per_player.c.has_pro_finish.is_(True), 1), else_=0)
                ),
                0,
            ).label("unique_pro_finishes"),
        )
        .select_from(per_player)
        .group_by(per_player.c.map_id)
        .order_by(per_player.c.map_id.asc())
    )

    rows = (await session.exec(statement)).all()
    values: list[dict[str, object]] = []
    for (
        map_id,
        unique_nub_finishes,
        total_finishes,
        total_playtime,
        average_first_completion_time,
        median_first_completion_time,
        average_playtime_per_player,
        median_playtime_per_player,
        average_finishes_per_player,
        median_finishes_per_player,
        unique_pro_finishes,
    ) in rows:
        resolved_unique_nub_finishes = int(unique_nub_finishes or 0)
        resolved_total_finishes = int(total_finishes or 0)
        resolved_total_playtime = round(float(total_playtime or 0), 3)
        resolved_average_first_completion_time = round(
            float(average_first_completion_time or 0), 3
        )
        resolved_median_first_completion_time = round(
            float(median_first_completion_time or 0), 3
        )
        resolved_average_playtime_per_player = round(
            float(average_playtime_per_player or 0), 3
        )
        resolved_median_playtime_per_player = round(
            float(median_playtime_per_player or 0), 3
        )
        resolved_average_finishes_per_player = round(
            float(average_finishes_per_player or 0), 2
        )
        resolved_median_finishes_per_player = round(
            float(median_finishes_per_player or 0), 2
        )
        resolved_unique_pro_finishes = int(unique_pro_finishes or 0)
        resolved_pro_nub_ratio = (
            round(resolved_unique_pro_finishes / resolved_unique_nub_finishes, 4)
            if resolved_unique_nub_finishes > 0
            else 0.0
        )
        values.append(
            {
                "map_id": int(map_id),
                "scope": scope,
                "total_finishes": resolved_total_finishes,
                "total_playtime": resolved_total_playtime,
                "average_first_completion_time": resolved_average_first_completion_time,
                "median_first_completion_time": resolved_median_first_completion_time,
                "average_playtime_per_player": resolved_average_playtime_per_player,
                "median_playtime_per_player": resolved_median_playtime_per_player,
                "average_finishes_per_player": resolved_average_finishes_per_player,
                "median_finishes_per_player": resolved_median_finishes_per_player,
                "pro_nub_ratio": resolved_pro_nub_ratio,
                "unique_pro_finishes": resolved_unique_pro_finishes,
                "unique_nub_finishes": resolved_unique_nub_finishes,
                "updated_at": now,
            }
        )
    return values


async def rebuild_map_leaderboards(
    *,
    session: AsyncSession,
    scopes: Iterable[ModeScope] | None = None,
    map_ids: Sequence[int] | None = None,
) -> int:
    normalized_scopes = _normalize_scope_list(scopes)
    target_map_ids = await _load_target_map_ids(session=session, map_ids=map_ids)
    if not normalized_scopes or not target_map_ids:
        return 0

    cache_table = MapLeaderboardCache.__table__  # type: ignore[attr-defined]
    processed = 0
    for scope in normalized_scopes:
        await session.exec(
            delete(MapLeaderboardCache).where(
                col(MapLeaderboardCache.scope) == scope,
                col(MapLeaderboardCache.map_id).in_(target_map_ids),
            )
        )
        values = await _build_map_leaderboard_values_for_scope(
            session=session,
            scope=scope,
            map_ids=target_map_ids,
        )
        if values:
            insert_statement = pg_insert(cache_table).values(values)
            await session.exec(insert_statement)
        processed += len(target_map_ids)

    return processed


async def rebuild_map_leaderboards_for_keys(
    *,
    session: AsyncSession,
    keys: Sequence[tuple[int, int]],
) -> int:
    normalized_keys = list(dict.fromkeys(keys))
    if not normalized_keys:
        return 0

    map_ids_by_scope: dict[ModeScope, list[int]] = defaultdict(list)
    for map_id, scope_id in normalized_keys:
        map_ids_by_scope[ModeScope[ModeScopeId(scope_id).name]].append(map_id)

    processed = 0
    for scope, scope_map_ids in map_ids_by_scope.items():
        processed += await rebuild_map_leaderboards(
            session=session,
            scopes=[scope],
            map_ids=scope_map_ids,
        )

    return processed


async def load_changed_map_leaderboard_keys(
    *,
    session: AsyncSession,
    window_start: datetime,
    window_end: datetime,
) -> list[tuple[int, int]]:
    rows = (
        await session.exec(
            select(Record.map_id, Record.mode_id)
            .where(
                col(Record.stage) == 0,
                col(Record.updated_at) >= window_start,
                col(Record.updated_at) < window_end,
            )
            .order_by(col(Record.map_id).asc(), col(Record.mode_id).asc())
        )
    ).all()
    return sorted(
        {
            (map_id, scope_id)
            for map_id, mode_id in rows
            for scope_id in _scope_ids_for_mode_id(mode_id)
        }
    )


async def read_map_leaderboard(
    *,
    session: AsyncSession,
    scope: ModeScope,
) -> MapLeaderboardsPublic:
    maps = (
        await session.exec(
            select(Map)
            .where(col(Map.validated).is_(True))
            .order_by(col(Map.name).asc(), col(Map.id).asc())
        )
    ).all()
    if not maps:
        return MapLeaderboardsPublic(data=[], count=0)

    map_ids = [map_obj.id for map_obj in maps]
    cache_rows_by_map_id = await _load_map_leaderboard_cache_rows(
        session=session,
        scope=scope,
        map_ids=map_ids,
    )
    tiers_by_map_id = await load_map_tiers_by_scope(session=session, map_ids=map_ids)
    review_summaries_by_map_id = await load_map_review_summaries(
        session=session,
        map_ids=map_ids,
    )

    data = []
    for map_obj in maps:
        cache_row = cache_rows_by_map_id.get(map_obj.id)
        map_tiers = tiers_by_map_id.get(map_obj.id)
        tier = getattr(map_tiers, scope.value) if map_tiers is not None else None
        data.append(
            MapLeaderboardEntryPublic(
                map=MapRefPublic(id=map_obj.id, name=map_obj.name),
                tier=tier,
                review_summary=review_summaries_by_map_id.get(map_obj.id),
                total_finishes=cache_row.total_finishes if cache_row is not None else 0,
                total_playtime=cache_row.total_playtime if cache_row is not None else 0,
                average_first_completion_time=(
                    cache_row.average_first_completion_time if cache_row is not None else 0
                ),
                median_first_completion_time=(
                    cache_row.median_first_completion_time if cache_row is not None else 0
                ),
                average_playtime_per_player=(
                    cache_row.average_playtime_per_player if cache_row is not None else 0
                ),
                median_playtime_per_player=(
                    cache_row.median_playtime_per_player if cache_row is not None else 0
                ),
                average_finishes_per_player=(
                    cache_row.average_finishes_per_player if cache_row is not None else 0
                ),
                median_finishes_per_player=(
                    cache_row.median_finishes_per_player if cache_row is not None else 0
                ),
                pro_nub_ratio=cache_row.pro_nub_ratio if cache_row is not None else 0,
                unique_pro_finishes=(
                    cache_row.unique_pro_finishes if cache_row is not None else 0
                ),
                unique_nub_finishes=(
                    cache_row.unique_nub_finishes if cache_row is not None else 0
                ),
                updated_at=cache_row.updated_at if cache_row is not None else None,
            )
        )

    return MapLeaderboardsPublic(data=data, count=len(data))
