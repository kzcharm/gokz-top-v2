from datetime import UTC, date, datetime, time
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Date, cast, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    PlayerDailyActivityContentPublic,
    PlayerDailyActivityDayPublic,
    PlayerDailyActivityPublic,
    PlayerDailyActivityStatPublic,
    PlayerPlaytimeCacheContent,
    PlayerPlaytimeContentPublic,
    PlayerPlaytimeCursor,
    PlayerPlaytimePublic,
    PlayerPlaytimeStatPublic,
    PlayerStatCache,
    PlayerStatsPublic,
    PlayerStatType,
    Record,
    get_datetime_utc,
)


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


def _normalize_daily_activity_content(content: Any) -> PlayerDailyActivityContentPublic:
    try:
        return PlayerDailyActivityContentPublic.model_validate(content)
    except ValidationError:
        return PlayerDailyActivityContentPublic()


def _serialize_daily_activity_content(
    content: PlayerDailyActivityContentPublic,
) -> dict[str, Any]:
    return content.model_dump(mode="json")


def _normalize_playtime_cache_content(content: Any) -> PlayerPlaytimeCacheContent:
    try:
        return PlayerPlaytimeCacheContent.model_validate(content)
    except ValidationError:
        return PlayerPlaytimeCacheContent()


def _serialize_playtime_cache_content(
    content: PlayerPlaytimeCacheContent,
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


def _to_player_playtime_stat_public(
    cache_row: PlayerStatCache,
) -> PlayerPlaytimeStatPublic:
    content = _normalize_playtime_cache_content(cache_row.content)
    return PlayerPlaytimeStatPublic(
        steamid64=str(cache_row.steamid64),
        type=cache_row.type,
        updated_at=cache_row.updated_at,
        content=PlayerPlaytimeContentPublic(total_seconds=content.total_seconds),
    )


async def _load_daily_activity_days(
    *,
    session: AsyncSession,
    steamid64: int,
    start_date: date | None = None,
) -> list[PlayerDailyActivityDayPublic]:
    record_date = _record_utc_date_expression()
    statement = select(record_date, func.count()).where(
        col(Record.steamid64) == steamid64
    )
    if start_date is not None:
        statement = statement.where(
            col(Record.created_at) >= _start_datetime_for_utc_date(start_date)
        )
    statement = statement.group_by(record_date).order_by(record_date)
    rows = (await session.exec(statement)).all()
    return [
        PlayerDailyActivityDayPublic(date=row[0], count=int(row[1])) for row in rows
    ]


async def _load_playtime_day_totals(
    *,
    session: AsyncSession,
    steamid64: int,
    start_date: date | None = None,
) -> list[tuple[date, Decimal]]:
    record_date = _record_utc_date_expression()
    statement = select(
        record_date,
        func.coalesce(func.sum(col(Record.time)), 0),
    ).where(col(Record.steamid64) == steamid64)
    if start_date is not None:
        statement = statement.where(
            col(Record.created_at) >= _start_datetime_for_utc_date(start_date)
        )
    statement = statement.group_by(record_date).order_by(record_date)
    rows = (await session.exec(statement)).all()
    return [(row[0], Decimal(row[1])) for row in rows]


async def _upsert_player_stat_cache(
    *,
    session: AsyncSession,
    steamid64: int,
    stat_type: PlayerStatType,
    content: dict[str, Any],
    updated_at: datetime,
) -> PlayerStatCache:
    cache_table = PlayerStatCache.__table__  # type: ignore[attr-defined]
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
    cache_row = await session.get(
        PlayerStatCache,
        (steamid64, PlayerStatType.DAILY_ACTIVITY),
    )
    cached_content = (
        _normalize_daily_activity_content(cache_row.content)
        if cache_row is not None
        else PlayerDailyActivityContentPublic()
    )
    latest_cached_day = (
        cached_content.days[-1].date if len(cached_content.days) > 0 else None
    )
    refreshed_days = await _load_daily_activity_days(
        session=session,
        steamid64=steamid64,
        start_date=latest_cached_day,
    )
    merged_days = (
        [day for day in cached_content.days if day.date < latest_cached_day]
        + refreshed_days
        if latest_cached_day is not None
        else refreshed_days
    )
    persisted = await _upsert_player_stat_cache(
        session=session,
        steamid64=steamid64,
        stat_type=PlayerStatType.DAILY_ACTIVITY,
        content=_serialize_daily_activity_content(
            PlayerDailyActivityContentPublic(days=merged_days)
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
    cache_row = await session.get(
        PlayerStatCache,
        (steamid64, PlayerStatType.PLAYTIME),
    )
    cached_content = (
        _normalize_playtime_cache_content(cache_row.content)
        if cache_row is not None
        else PlayerPlaytimeCacheContent()
    )
    cursor = cached_content.cursor
    refreshed_day_totals = await _load_playtime_day_totals(
        session=session,
        steamid64=steamid64,
        start_date=cursor.latest_day if cursor is not None else None,
    )

    if cursor is None:
        base_total_before_latest_day = Decimal("0")
    else:
        base_total_before_latest_day = Decimal(str(cursor.total_before_latest_day))

    tail_total = sum((day_total for _, day_total in refreshed_day_totals), Decimal("0"))
    total_seconds = _quantize_seconds(base_total_before_latest_day + tail_total)

    if refreshed_day_totals:
        latest_day = refreshed_day_totals[-1][0]
        total_before_latest_day = _quantize_seconds(
            base_total_before_latest_day
            + sum(
                (day_total for _, day_total in refreshed_day_totals[:-1]),
                Decimal("0"),
            )
        )
        next_cursor = PlayerPlaytimeCursor(
            latest_day=latest_day,
            total_before_latest_day=total_before_latest_day,
        )
    else:
        next_cursor = None

    persisted = await _upsert_player_stat_cache(
        session=session,
        steamid64=steamid64,
        stat_type=PlayerStatType.PLAYTIME,
        content=_serialize_playtime_cache_content(
            PlayerPlaytimeCacheContent(
                total_seconds=total_seconds,
                cursor=next_cursor,
            )
        ),
        updated_at=now or get_datetime_utc(),
    )
    return _to_player_playtime_stat_public(persisted)


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
    if cache_row is not None and cache_row.updated_at >= get_utc_midnight(
        now=current_now
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
    current_now = now or get_datetime_utc()
    cache_row = await session.get(
        PlayerStatCache,
        (steamid64, PlayerStatType.PLAYTIME),
    )
    if cache_row is not None and cache_row.updated_at >= get_utc_midnight(
        now=current_now
    ):
        return _to_player_playtime_stat_public(cache_row)

    return await rebuild_player_playtime_stat(
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
        playtime = await get_or_rebuild_player_playtime_stat(
            session=session,
            steamid64=steamid64,
            now=current_now,
        )
        payload.playtime = PlayerPlaytimePublic(
            updated_at=playtime.updated_at,
            total_seconds=playtime.content.total_seconds,
        )

    return payload
