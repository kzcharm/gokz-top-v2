from datetime import UTC, date, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Date, cast, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    PlayerDailyActivityContentPublic,
    PlayerDailyActivityDayPublic,
    PlayerDailyActivityStatPublic,
    PlayerStatCache,
    PlayerStatType,
    Record,
    get_datetime_utc,
)


def get_utc_midnight(*, now: datetime | None = None) -> datetime:
    current = now or get_datetime_utc()
    normalized = current.astimezone(UTC) if current.tzinfo else current.replace(tzinfo=UTC)
    return normalized.replace(hour=0, minute=0, second=0, microsecond=0)


def _normalize_daily_activity_content(content: Any) -> PlayerDailyActivityContentPublic:
    try:
        return PlayerDailyActivityContentPublic.model_validate(content)
    except ValidationError:
        return PlayerDailyActivityContentPublic()


def _serialize_daily_activity_content(
    content: PlayerDailyActivityContentPublic,
) -> dict[str, Any]:
    return content.model_dump(mode="json")


def _to_player_daily_activity_stat_public(
    cache_row: PlayerStatCache,
) -> PlayerDailyActivityStatPublic:
    return PlayerDailyActivityStatPublic(
        steamid64=str(cache_row.steamid64),
        type=cache_row.type,
        updated_at=cache_row.updated_at,
        content=_normalize_daily_activity_content(cache_row.content),
    )


async def _load_daily_activity_days(
    *,
    session: AsyncSession,
    steamid64: int,
    start_date: date | None = None,
) -> list[PlayerDailyActivityDayPublic]:
    record_date = cast(func.timezone("UTC", col(Record.created_at)), Date)
    statement = select(record_date, func.count()).where(col(Record.steamid64) == steamid64)
    if start_date is not None:
        statement = statement.where(record_date >= start_date)
    statement = statement.group_by(record_date).order_by(record_date)
    rows = (await session.exec(statement)).all()
    return [PlayerDailyActivityDayPublic(date=row[0], count=int(row[1])) for row in rows]


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
        [day for day in cached_content.days if day.date < latest_cached_day] + refreshed_days
        if latest_cached_day is not None
        else refreshed_days
    )
    merged_content = PlayerDailyActivityContentPublic(days=merged_days)
    updated_at = now or get_datetime_utc()

    cache_table = PlayerStatCache.__table__  # type: ignore[attr-defined]
    values = {
        "steamid64": steamid64,
        "type": PlayerStatType.DAILY_ACTIVITY,
        "content": _serialize_daily_activity_content(merged_content),
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

    persisted = await session.get(
        PlayerStatCache,
        (steamid64, PlayerStatType.DAILY_ACTIVITY),
    )
    assert persisted is not None
    return _to_player_daily_activity_stat_public(persisted)


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
    if cache_row is not None and cache_row.updated_at >= get_utc_midnight(now=current_now):
        return _to_player_daily_activity_stat_public(cache_row)

    return await rebuild_player_daily_activity_stat(
        session=session,
        steamid64=steamid64,
        now=current_now,
    )
