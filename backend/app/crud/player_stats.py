import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Date, String, cast, func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import col
from sqlmodel.ext.asyncio.session import AsyncSession

from app.crud.player_profile_field_change import player_action_timestamp_exists
from app.models import (
    Map,
    Player,
    PlayerAction,
    PlayerDailyActivityContentPublic,
    PlayerDailyActivityDayPublic,
    PlayerDailyActivityPublic,
    PlayerDailyActivityStatPublic,
    PlayerMostPlayedMapEntryPublic,
    PlayerMostPlayedMapsContentPublic,
    PlayerMostPlayedMapsPeriodPublic,
    PlayerMostPlayedMapsPublic,
    PlayerMostPlayedMapsStatPublic,
    PlayerMostPlayedServerContentPublic,
    PlayerMostPlayedServerEntryPublic,
    PlayerMostPlayedServerPeriodPublic,
    PlayerMostPlayedServerPublic,
    PlayerMostPlayedServerStatPublic,
    PlayerPlaytimeContentPublic,
    PlayerPlaytimePublic,
    PlayerPlaytimeStatPublic,
    PlayerStatCache,
    PlayerStatsPublic,
    PlayerStatType,
    Record,
    ServerGlobalapi,
    ServerGroup,
    get_datetime_utc,
)
from app.models.utils import get_sqlmodel_table, select_row

MOST_PLAYED_MAPS_ENTRY_LIMIT = 10
DAILY_ACTIVITY_CACHE_VERSION = 2


def get_utc_midnight(*, now: datetime | None = None) -> datetime:
    current = now or get_datetime_utc()
    normalized = (
        current.astimezone(UTC) if current.tzinfo else current.replace(tzinfo=UTC)
    )
    return normalized.replace(hour=0, minute=0, second=0, microsecond=0)


def _record_utc_date_expression() -> Any:
    return cast(func.timezone("UTC", col(Record.created_at)), Date)


def _start_datetime_for_utc_date(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=UTC)


def _quantize_seconds(value: Decimal | float | int | str) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))


def _to_utc_datetime(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _normalize_daily_activity_content(content: Any) -> PlayerDailyActivityContentPublic:
    try:
        return PlayerDailyActivityContentPublic.model_validate(content)
    except ValidationError:
        return PlayerDailyActivityContentPublic()


def _serialize_daily_activity_content(
    content: PlayerDailyActivityContentPublic,
) -> dict[str, Any]:
    return {**content.model_dump(mode="json"), "version": DAILY_ACTIVITY_CACHE_VERSION}


def _normalize_most_played_server_content(
    content: Any,
) -> PlayerMostPlayedServerContentPublic:
    try:
        return PlayerMostPlayedServerContentPublic.model_validate(content)
    except ValidationError:
        return PlayerMostPlayedServerContentPublic()


def _serialize_most_played_server_content(
    content: PlayerMostPlayedServerContentPublic,
) -> dict[str, Any]:
    return content.model_dump(mode="json", exclude_none=True)


def _normalize_most_played_maps_content(
    content: Any,
) -> PlayerMostPlayedMapsContentPublic:
    try:
        return PlayerMostPlayedMapsContentPublic.model_validate(content)
    except ValidationError:
        return PlayerMostPlayedMapsContentPublic()


def _serialize_most_played_maps_content(
    content: PlayerMostPlayedMapsContentPublic,
) -> dict[str, Any]:
    return content.model_dump(mode="json", exclude_none=True)


def _to_player_daily_activity_stat_public(
    cache_row: PlayerStatCache,
) -> PlayerDailyActivityStatPublic:
    return PlayerDailyActivityStatPublic(
        steamid64=str(cache_row.steamid64),
        type=cache_row.type,
        updated_at=cache_row.updated_at,
        content=_normalize_daily_activity_content(cache_row.content),
    )


def _to_player_most_played_server_stat_public(
    cache_row: PlayerStatCache,
) -> PlayerMostPlayedServerStatPublic:
    return PlayerMostPlayedServerStatPublic(
        steamid64=str(cache_row.steamid64),
        type=cache_row.type,
        updated_at=cache_row.updated_at,
        content=_normalize_most_played_server_content(cache_row.content),
    )


def _to_player_most_played_maps_stat_public(
    cache_row: PlayerStatCache,
) -> PlayerMostPlayedMapsStatPublic:
    return PlayerMostPlayedMapsStatPublic(
        steamid64=str(cache_row.steamid64),
        type=cache_row.type,
        updated_at=cache_row.updated_at,
        content=_normalize_most_played_maps_content(cache_row.content),
    )


@dataclass(slots=True)
class _MostPlayedServerBucket:
    key: str
    label: str
    group_id: str | None
    server_ids: set[int | uuid.UUID]
    total_seconds: Decimal


@dataclass(slots=True)
class _MostPlayedMapBucket:
    map_id: int
    map_name: str
    map_tier: int | None
    record_count: int
    total_seconds: Decimal


def _bucket_sort_key(bucket: _MostPlayedServerBucket) -> tuple[Decimal, str, str]:
    return (-bucket.total_seconds, bucket.label.casefold(), bucket.key)


def _most_played_map_records_sort_key(
    bucket: _MostPlayedMapBucket,
) -> tuple[int, Decimal, str, int]:
    return (
        -bucket.record_count,
        -bucket.total_seconds,
        bucket.map_name.casefold(),
        bucket.map_id,
    )


def _most_played_map_time_sort_key(
    bucket: _MostPlayedMapBucket,
) -> tuple[Decimal, int, str, int]:
    return (
        -bucket.total_seconds,
        -bucket.record_count,
        bucket.map_name.casefold(),
        bucket.map_id,
    )


def _build_most_played_server_entry(
    bucket: _MostPlayedServerBucket,
) -> PlayerMostPlayedServerEntryPublic:
    return PlayerMostPlayedServerEntryPublic(
        key=bucket.key,
        label=bucket.label,
        total_seconds=_quantize_seconds(bucket.total_seconds),
        server_count=len(bucket.server_ids),
        server_ids=sorted(
            value for value in bucket.server_ids if isinstance(value, int)
        ),
        native_server_ids=sorted(
            (value for value in bucket.server_ids if isinstance(value, uuid.UUID)),
            key=str,
        ),
        group_id=bucket.group_id,
    )


def _build_most_played_server_period_public(
    buckets: dict[str, _MostPlayedServerBucket],
) -> PlayerMostPlayedServerPeriodPublic:
    ordered_buckets = sorted(buckets.values(), key=_bucket_sort_key)
    total_seconds = sum(
        (bucket.total_seconds for bucket in ordered_buckets), Decimal("0")
    )
    return PlayerMostPlayedServerPeriodPublic(
        total_seconds=_quantize_seconds(total_seconds),
        entries=[_build_most_played_server_entry(bucket) for bucket in ordered_buckets],
    )


def _build_most_played_map_entry(
    bucket: _MostPlayedMapBucket,
) -> PlayerMostPlayedMapEntryPublic:
    return PlayerMostPlayedMapEntryPublic(
        map_id=bucket.map_id,
        map_name=bucket.map_name,
        map_tier=bucket.map_tier,
        record_count=bucket.record_count,
        total_seconds=_quantize_seconds(bucket.total_seconds),
    )


def _build_most_played_maps_period_public(
    buckets: dict[int, _MostPlayedMapBucket],
) -> PlayerMostPlayedMapsPeriodPublic:
    by_records = sorted(buckets.values(), key=_most_played_map_records_sort_key)[
        :MOST_PLAYED_MAPS_ENTRY_LIMIT
    ]
    by_time = sorted(buckets.values(), key=_most_played_map_time_sort_key)[
        :MOST_PLAYED_MAPS_ENTRY_LIMIT
    ]
    total_records = sum(bucket.record_count for bucket in buckets.values())
    total_seconds = sum(
        (bucket.total_seconds for bucket in buckets.values()), Decimal("0")
    )
    return PlayerMostPlayedMapsPeriodPublic(
        total_records=total_records,
        total_seconds=_quantize_seconds(total_seconds),
        entries_by_records=[
            _build_most_played_map_entry(bucket) for bucket in by_records
        ],
        entries_by_time=[_build_most_played_map_entry(bucket) for bucket in by_time],
    )


def _favorite_target_from_most_played_entry(
    entry: PlayerMostPlayedServerEntryPublic,
) -> tuple[int | None, uuid.UUID | None]:
    if entry.key.startswith("group:") and entry.group_id is not None:
        return None, uuid.UUID(entry.group_id)

    if entry.key.startswith("server:") and entry.server_ids:
        return entry.server_ids[0], None

    return None, None


async def _auto_update_player_favorite_server(
    *,
    session: AsyncSession,
    steamid64: int,
    content: PlayerMostPlayedServerContentPublic,
    updated_at: datetime,
) -> None:
    manual_override_exists = await player_action_timestamp_exists(
        session=session,
        player_steamid64=steamid64,
        action=PlayerAction.FAVORITE_SERVER_MANUAL_OVERRIDE,
    )
    if manual_override_exists:
        return

    player = await session.get(Player, steamid64)
    if player is None:
        return

    top_entry = (
        content.all_time.entries[0] if len(content.all_time.entries) > 0 else None
    )
    favorite_server_id: int | None = None
    favorite_server_group_id: uuid.UUID | None = None
    if top_entry is not None:
        favorite_server_id, favorite_server_group_id = (
            _favorite_target_from_most_played_entry(top_entry)
        )

    if (
        player.favorite_server_id == favorite_server_id
        and player.favorite_server_group_id == favorite_server_group_id
    ):
        return

    player.favorite_server_id = favorite_server_id
    player.favorite_server_group_id = favorite_server_group_id
    player.updated_at = updated_at
    session.add(player)
    await session.commit()
    await session.refresh(player)


# Aggregate ranges once; multirange containment avoids a session lookup per run.
DAILY_ACTIVITY_SQL = """
WITH windows AS MATERIALIZED (
    SELECT COALESCE(range_agg(tstzrange(connected_at, disconnect_at, '[]')),
                    '{{}}'::tstzmultirange) AS spans
    FROM player_session
    WHERE player_steamid64 = :steamid64 AND disconnect_at IS NOT NULL {window_filter}
), record_days AS (
    SELECT (created_at AT TIME ZONE 'UTC')::date AS day,
           count(*) AS count,
           sum(CASE WHEN spans @> created_at THEN 0 ELSE time END) AS seconds
    FROM record CROSS JOIN windows
    WHERE steamid64 = :steamid64 {record_filter}
    GROUP BY 1
), session_days AS (
    SELECT day::date AS day, 0::bigint AS count,
           sum(EXTRACT(EPOCH FROM (
               least(upper(span), (day + interval '1 day') AT TIME ZONE 'UTC')
               - greatest(lower(span), day AT TIME ZONE 'UTC')
           ))) AS seconds
    FROM windows CROSS JOIN LATERAL unnest(spans) AS span
    CROSS JOIN LATERAL generate_series(
        date_trunc('day', lower(span) AT TIME ZONE 'UTC'),
        date_trunc('day', upper(span) AT TIME ZONE 'UTC'), interval '1 day'
    ) AS day
    WHERE day AT TIME ZONE 'UTC' < upper(span) {session_filter}
    GROUP BY 1
)
SELECT day, sum(count)::bigint AS count, sum(seconds) AS seconds
FROM (SELECT * FROM record_days UNION ALL SELECT * FROM session_days) AS activity
GROUP BY day ORDER BY day
"""


async def _load_daily_activity_days(
    *,
    session: AsyncSession,
    steamid64: int,
    dates: list[date] | None = None,
) -> list[PlayerDailyActivityDayPublic]:
    record_filter = ""
    session_filter = ""
    window_filter = ""
    params: dict[str, Any] = {"steamid64": steamid64}
    if dates is not None:
        if not dates:
            return []
        params["dates"] = dates
        params["start"] = _start_datetime_for_utc_date(min(dates))
        params["end"] = _start_datetime_for_utc_date(max(dates) + timedelta(days=1))
        record_filter = """AND created_at >= :start AND created_at < :end
            AND (created_at AT TIME ZONE 'UTC')::date = ANY(:dates)"""
        session_filter = "AND day::date = ANY(:dates)"
        window_filter = "AND connected_at < :end AND disconnect_at >= :start"
    rows = (
        await session.execute(
            text(
                DAILY_ACTIVITY_SQL.format(
                    record_filter=record_filter,
                    session_filter=session_filter,
                    window_filter=window_filter,
                )
            ),
            params,
        )
    ).all()
    return [
        PlayerDailyActivityDayPublic(
            date=row.day,
            count=row.count,
            total_seconds=_quantize_seconds(row.seconds),
        )
        for row in rows
    ]


async def refresh_player_daily_activity_cache_dates(
    *,
    session: AsyncSession,
    steamid64: int,
    dates: set[date],
    now: datetime | None = None,
) -> None:
    requested_dates = sorted(dates)
    if not requested_dates:
        return

    cache_row = await session.get(
        PlayerStatCache,
        (steamid64, PlayerStatType.DAILY_ACTIVITY),
    )
    if cache_row is None:
        return
    if cache_row.content.get("version") != DAILY_ACTIVITY_CACHE_VERSION:
        await session.delete(cache_row)
        return

    await session.flush()

    cached_content = _normalize_daily_activity_content(cache_row.content)
    days_by_date = {day.date: day for day in cached_content.days}
    refreshed = {
        day.date: day
        for day in await _load_daily_activity_days(
            session=session,
            steamid64=steamid64,
            dates=requested_dates,
        )
    }
    for requested_date in requested_dates:
        if requested_date in refreshed:
            days_by_date[requested_date] = refreshed[requested_date]
        else:
            days_by_date.pop(requested_date, None)

    cache_row.content = _serialize_daily_activity_content(
        PlayerDailyActivityContentPublic(
            days=[days_by_date[key] for key in sorted(days_by_date)]
        )
    )
    current_now = now or get_datetime_utc()
    if cache_row.updated_at >= get_utc_midnight(now=current_now):
        cache_row.updated_at = current_now
    session.add(cache_row)


async def _upsert_player_stat_cache(
    *,
    session: AsyncSession,
    steamid64: int,
    stat_type: PlayerStatType,
    content: dict[str, Any],
    updated_at: datetime,
) -> PlayerStatCache:
    cache_table = get_sqlmodel_table(PlayerStatCache)
    values = {
        "steamid64": steamid64,
        "type": stat_type,
        "content": content,
        "updated_at": updated_at,
    }
    insert_statement = pg_insert(cache_table).values(values)
    upsert_statement = insert_statement.on_conflict_do_update(
        index_elements=[cache_table.c.steamid64, cache_table.c.type],
        set_={
            "content": insert_statement.excluded.content,
            "updated_at": insert_statement.excluded.updated_at,
        },
    )
    await session.exec(upsert_statement)
    await session.commit()

    persisted = await session.get(PlayerStatCache, (steamid64, stat_type))
    assert persisted is not None
    await session.refresh(persisted)
    return persisted


async def rebuild_player_daily_activity_stat(
    *,
    session: AsyncSession,
    steamid64: int,
    now: datetime | None = None,
) -> PlayerDailyActivityStatPublic:
    refreshed_days = await _load_daily_activity_days(
        session=session,
        steamid64=steamid64,
    )
    persisted = await _upsert_player_stat_cache(
        session=session,
        steamid64=steamid64,
        stat_type=PlayerStatType.DAILY_ACTIVITY,
        content=_serialize_daily_activity_content(
            PlayerDailyActivityContentPublic(days=refreshed_days)
        ),
        updated_at=now or get_datetime_utc(),
    )
    return _to_player_daily_activity_stat_public(persisted)


async def rebuild_player_playtime_stat(
    *,
    session: AsyncSession,
    steamid64: int,
    now: datetime | None = None,
) -> PlayerPlaytimeStatPublic:
    activity = await rebuild_player_daily_activity_stat(
        session=session,
        steamid64=steamid64,
        now=now,
    )
    return _playtime_from_activity(activity)


def _playtime_from_activity(
    activity: PlayerDailyActivityStatPublic,
) -> PlayerPlaytimeStatPublic:
    return PlayerPlaytimeStatPublic(
        steamid64=activity.steamid64,
        type=PlayerStatType.PLAYTIME,
        updated_at=activity.updated_at,
        content=PlayerPlaytimeContentPublic(
            total_seconds=_quantize_seconds(
                sum(
                    (Decimal(str(day.total_seconds)) for day in activity.content.days),
                    Decimal(0),
                )
            )
        ),
    )


async def _load_most_played_server_rows(
    *,
    session: AsyncSession,
    steamid64: int,
) -> list[tuple[datetime, Decimal, int | uuid.UUID, str | None, Any, str | None]]:
    statement = (
        select_row(
            col(Record.created_at),
            col(Record.time),
            func.coalesce(
                cast(col(Record.server_id), String),
                cast(col(Record.native_server_id), String),
            ),
            func.coalesce(col(ServerGlobalapi.name), Record.native_server_name),
            func.coalesce(col(ServerGlobalapi.group_id), Record.native_group_id),
            col(ServerGroup.name),
        )
        .outerjoin(ServerGlobalapi, col(Record.server_id) == col(ServerGlobalapi.id))
        .outerjoin(
            ServerGroup,
            func.coalesce(col(ServerGlobalapi.group_id), Record.native_group_id)
            == col(ServerGroup.id),
        )
        .where(col(Record.steamid64) == steamid64)
        .order_by(col(Record.created_at).asc(), col(Record.id).asc())
    )
    rows = (await session.exec(statement)).all()
    return [
        (
            row[0],
            Decimal(row[1]),
            uuid.UUID(row[2]) if "-" in row[2] else int(row[2]),
            row[3],
            row[4],
            row[5],
        )
        for row in rows
    ]


async def _load_most_played_map_rows(
    *,
    session: AsyncSession,
    steamid64: int,
) -> list[tuple[datetime, Decimal, int, str, int | None]]:
    statement = (
        select_row(
            col(Record.created_at),
            col(Record.time),
            col(Map.id),
            col(Map.name),
            col(Map.difficulty),
        )
        .join(Map, col(Record.map_id) == col(Map.id))
        .where(col(Record.steamid64) == steamid64)
        .order_by(col(Record.created_at).asc(), col(Record.id).asc())
    )
    rows = (await session.exec(statement)).all()
    return [
        (
            row[0],
            Decimal(row[1]),
            int(row[2]),
            str(row[3]),
            int(row[4]) if row[4] is not None else None,
        )
        for row in rows
    ]


async def rebuild_player_most_played_server_stat(
    *,
    session: AsyncSession,
    steamid64: int,
    now: datetime | None = None,
) -> PlayerMostPlayedServerStatPublic:
    current_now = _to_utc_datetime(now or get_datetime_utc())
    rows = await _load_most_played_server_rows(
        session=session,
        steamid64=steamid64,
    )

    first_year = _to_utc_datetime(rows[0][0]).year if rows else None
    current_year = current_now.year
    years = list(range(first_year, current_year + 1)) if first_year is not None else []
    rolling_start = current_now - timedelta(days=365)

    all_time_buckets: dict[str, _MostPlayedServerBucket] = {}
    last_365_days_buckets: dict[str, _MostPlayedServerBucket] = {}
    yearly_buckets: dict[int, dict[str, _MostPlayedServerBucket]] = {
        year: {} for year in years
    }

    def add_bucket(
        bucket_map: dict[str, _MostPlayedServerBucket],
        *,
        bucket_key: str,
        label: str,
        group_id: str | None,
        server_id: int | uuid.UUID,
        total_seconds: Decimal,
    ) -> None:
        bucket = bucket_map.get(bucket_key)
        if bucket is None:
            bucket_map[bucket_key] = _MostPlayedServerBucket(
                key=bucket_key,
                label=label,
                group_id=group_id,
                server_ids={server_id},
                total_seconds=total_seconds,
            )
            return

        bucket.server_ids.add(server_id)
        bucket.total_seconds += total_seconds

    for (
        created_at,
        record_time,
        server_id,
        server_name,
        raw_group_id,
        group_name,
    ) in rows:
        record_at = _to_utc_datetime(created_at)
        group_id = str(raw_group_id) if raw_group_id is not None else None
        bucket_key = (
            f"group:{group_id}" if group_id is not None else f"server:{server_id}"
        )
        label = (
            group_name
            or server_name
            or (
                f"Server Group {group_id}"
                if group_id is not None
                else f"Server #{server_id}"
            )
        )
        total_seconds = Decimal(str(record_time))

        add_bucket(
            all_time_buckets,
            bucket_key=bucket_key,
            label=label,
            group_id=group_id,
            server_id=server_id,
            total_seconds=total_seconds,
        )
        if record_at >= rolling_start:
            add_bucket(
                last_365_days_buckets,
                bucket_key=bucket_key,
                label=label,
                group_id=group_id,
                server_id=server_id,
                total_seconds=total_seconds,
            )
        if record_at.year in yearly_buckets:
            add_bucket(
                yearly_buckets[record_at.year],
                bucket_key=bucket_key,
                label=label,
                group_id=group_id,
                server_id=server_id,
                total_seconds=total_seconds,
            )

    content = PlayerMostPlayedServerContentPublic(
        first_year=first_year,
        current_year=current_year if first_year is not None else None,
        years=years,
        all_time=_build_most_played_server_period_public(all_time_buckets),
        last_365_days=_build_most_played_server_period_public(last_365_days_buckets),
        yearly={
            str(year): _build_most_played_server_period_public(yearly_buckets[year])
            for year in years
        },
    )
    persisted = await _upsert_player_stat_cache(
        session=session,
        steamid64=steamid64,
        stat_type=PlayerStatType.MOST_PLAYED_SERVER,
        content=_serialize_most_played_server_content(content),
        updated_at=current_now,
    )
    await _auto_update_player_favorite_server(
        session=session,
        steamid64=steamid64,
        content=content,
        updated_at=current_now,
    )
    return _to_player_most_played_server_stat_public(persisted)


async def rebuild_player_most_played_maps_stat(
    *,
    session: AsyncSession,
    steamid64: int,
    now: datetime | None = None,
) -> PlayerMostPlayedMapsStatPublic:
    current_now = _to_utc_datetime(now or get_datetime_utc())
    rows = await _load_most_played_map_rows(
        session=session,
        steamid64=steamid64,
    )

    first_year = _to_utc_datetime(rows[0][0]).year if rows else None
    current_year = current_now.year
    years = list(range(first_year, current_year + 1)) if first_year is not None else []
    rolling_start = current_now - timedelta(days=365)

    all_time_buckets: dict[int, _MostPlayedMapBucket] = {}
    last_365_days_buckets: dict[int, _MostPlayedMapBucket] = {}
    yearly_buckets: dict[int, dict[int, _MostPlayedMapBucket]] = {
        year: {} for year in years
    }

    def add_bucket(
        bucket_map: dict[int, _MostPlayedMapBucket],
        *,
        map_id: int,
        map_name: str,
        map_tier: int | None,
        total_seconds: Decimal,
    ) -> None:
        bucket = bucket_map.get(map_id)
        if bucket is None:
            bucket_map[map_id] = _MostPlayedMapBucket(
                map_id=map_id,
                map_name=map_name,
                map_tier=map_tier,
                record_count=1,
                total_seconds=total_seconds,
            )
            return

        bucket.record_count += 1
        bucket.total_seconds += total_seconds

    for created_at, record_time, map_id, map_name, map_tier in rows:
        record_at = _to_utc_datetime(created_at)
        total_seconds = Decimal(str(record_time))

        add_bucket(
            all_time_buckets,
            map_id=map_id,
            map_name=map_name,
            map_tier=map_tier,
            total_seconds=total_seconds,
        )
        if record_at >= rolling_start:
            add_bucket(
                last_365_days_buckets,
                map_id=map_id,
                map_name=map_name,
                map_tier=map_tier,
                total_seconds=total_seconds,
            )
        if record_at.year in yearly_buckets:
            add_bucket(
                yearly_buckets[record_at.year],
                map_id=map_id,
                map_name=map_name,
                map_tier=map_tier,
                total_seconds=total_seconds,
            )

    content = PlayerMostPlayedMapsContentPublic(
        first_year=first_year,
        current_year=current_year if first_year is not None else None,
        years=years,
        all_time=_build_most_played_maps_period_public(all_time_buckets),
        last_365_days=_build_most_played_maps_period_public(last_365_days_buckets),
        yearly={
            str(year): _build_most_played_maps_period_public(yearly_buckets[year])
            for year in years
        },
    )
    persisted = await _upsert_player_stat_cache(
        session=session,
        steamid64=steamid64,
        stat_type=PlayerStatType.MOST_PLAYED_MAPS,
        content=_serialize_most_played_maps_content(content),
        updated_at=current_now,
    )
    return _to_player_most_played_maps_stat_public(persisted)


async def get_or_rebuild_player_daily_activity_stat(
    *,
    session: AsyncSession,
    steamid64: int,
    now: datetime | None = None,
) -> PlayerDailyActivityStatPublic:
    current_now = now or get_datetime_utc()
    cache_row = await session.get(
        PlayerStatCache,
        (steamid64, PlayerStatType.DAILY_ACTIVITY),
    )
    if (
        cache_row is not None
        and cache_row.content.get("version") == DAILY_ACTIVITY_CACHE_VERSION
        and cache_row.updated_at >= get_utc_midnight(now=current_now)
    ):
        return _to_player_daily_activity_stat_public(cache_row)

    return await rebuild_player_daily_activity_stat(
        session=session,
        steamid64=steamid64,
        now=current_now,
    )


async def get_or_rebuild_player_playtime_stat(
    *,
    session: AsyncSession,
    steamid64: int,
    now: datetime | None = None,
) -> PlayerPlaytimeStatPublic:
    return _playtime_from_activity(
        await get_or_rebuild_player_daily_activity_stat(
            session=session,
            steamid64=steamid64,
            now=now,
        )
    )


async def get_or_rebuild_player_most_played_server_stat(
    *,
    session: AsyncSession,
    steamid64: int,
    now: datetime | None = None,
) -> PlayerMostPlayedServerStatPublic:
    current_now = now or get_datetime_utc()
    cache_row = await session.get(
        PlayerStatCache,
        (steamid64, PlayerStatType.MOST_PLAYED_SERVER),
    )
    if cache_row is not None and cache_row.updated_at >= get_utc_midnight(
        now=current_now
    ):
        return _to_player_most_played_server_stat_public(cache_row)

    return await rebuild_player_most_played_server_stat(
        session=session,
        steamid64=steamid64,
        now=current_now,
    )


async def get_or_rebuild_player_most_played_maps_stat(
    *,
    session: AsyncSession,
    steamid64: int,
    now: datetime | None = None,
) -> PlayerMostPlayedMapsStatPublic:
    current_now = now or get_datetime_utc()
    cache_row = await session.get(
        PlayerStatCache,
        (steamid64, PlayerStatType.MOST_PLAYED_MAPS),
    )
    if cache_row is not None and cache_row.updated_at >= get_utc_midnight(
        now=current_now
    ):
        return _to_player_most_played_maps_stat_public(cache_row)

    return await rebuild_player_most_played_maps_stat(
        session=session,
        steamid64=steamid64,
        now=current_now,
    )


async def get_or_rebuild_player_stats(
    *,
    session: AsyncSession,
    steamid64: int,
    stat_type: PlayerStatType | None = None,
    now: datetime | None = None,
) -> PlayerStatsPublic:
    current_now = now or get_datetime_utc()
    requested_types = [stat_type] if stat_type is not None else list(PlayerStatType)
    payload = PlayerStatsPublic(steamid64=str(steamid64))

    if PlayerStatType.DAILY_ACTIVITY in requested_types:
        daily_activity = await get_or_rebuild_player_daily_activity_stat(
            session=session,
            steamid64=steamid64,
            now=current_now,
        )
        payload.daily_activity = PlayerDailyActivityPublic(
            updated_at=daily_activity.updated_at,
            days=daily_activity.content.days,
        )

    if PlayerStatType.PLAYTIME in requested_types:
        playtime = (
            _playtime_from_activity(daily_activity)
            if PlayerStatType.DAILY_ACTIVITY in requested_types
            else await get_or_rebuild_player_playtime_stat(
                session=session,
                steamid64=steamid64,
                now=current_now,
            )
        )
        payload.playtime = PlayerPlaytimePublic(
            updated_at=playtime.updated_at,
            total_seconds=playtime.content.total_seconds,
        )

    if PlayerStatType.MOST_PLAYED_SERVER in requested_types:
        most_played_server = await get_or_rebuild_player_most_played_server_stat(
            session=session,
            steamid64=steamid64,
            now=current_now,
        )
        payload.most_played_server = PlayerMostPlayedServerPublic(
            updated_at=most_played_server.updated_at,
            **most_played_server.content.model_dump(),
        )

    if PlayerStatType.MOST_PLAYED_MAPS in requested_types:
        most_played_maps = await get_or_rebuild_player_most_played_maps_stat(
            session=session,
            steamid64=steamid64,
            now=current_now,
        )
        payload.most_played_maps = PlayerMostPlayedMapsPublic(
            updated_at=most_played_maps.updated_at,
            **most_played_maps.content.model_dump(),
        )

    return payload
