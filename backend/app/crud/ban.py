from datetime import datetime
from typing import Any

from sqlalchemy import exists, func, not_, or_
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Ban, BanCompatPublicV0, BanListQuery, BanPublic, BanType
from app.models.utils import get_datetime_utc


def _parse_ban_type_values(
    *,
    ban_types: str | None,
    ban_types_list: list[str] | None,
) -> list[BanType]:
    values: list[BanType] = []
    raw_values: list[str] = []
    if ban_types:
        raw_values.extend(
            token.strip() for token in ban_types.split(",") if token.strip()
        )
    if ban_types_list:
        raw_values.extend(token.strip() for token in ban_types_list if token.strip())

    for raw in raw_values:
        try:
            values.append(BanType(raw))
        except ValueError:
            continue
    return list(dict.fromkeys(values))


def active_ban_exists_clause(
    *,
    steamid64_column: ColumnElement[Any],
    now: datetime | None = None,
) -> ColumnElement[bool]:
    current_time = now or get_datetime_utc()
    return exists(
        select(Ban.id).where(
            col(Ban.steamid64) == steamid64_column,
            or_(
                col(Ban.expires_on).is_(None),
                col(Ban.expires_on) >= current_time,
            ),
        )
    )


def not_active_ban_exists_clause(
    *,
    steamid64_column: ColumnElement[Any],
    now: datetime | None = None,
) -> ColumnElement[bool]:
    return not_(active_ban_exists_clause(steamid64_column=steamid64_column, now=now))


def to_ban_compat_public_v0(*, ban: Ban) -> BanCompatPublicV0:
    return BanCompatPublicV0(
        id=ban.id,
        ban_type=ban.ban_type,
        expires_on=ban.expires_on,
        ip=ban.ip,
        steamid64=str(ban.steamid64),
        player_name=ban.player_name,
        notes=ban.notes,
        stats=ban.stats,
        server_id=ban.server_id,
        updated_by_id=ban.updated_by_id,
        created_on=ban.created_on,
        updated_on=ban.updated_on,
    )


def to_ban_public(*, ban: Ban) -> BanPublic:
    compat = to_ban_compat_public_v0(ban=ban)
    return BanPublic.model_validate(compat.model_dump())


async def read_bans(
    *,
    session: AsyncSession,
    query: BanListQuery,
) -> tuple[list[Ban], int]:
    filters: list[ColumnElement[bool]] = []
    ban_type_values = _parse_ban_type_values(
        ban_types=query.ban_types,
        ban_types_list=query.ban_types_list,
    )

    if ban_type_values:
        filters.append(col(Ban.ban_type).in_(ban_type_values))
    elif query.ban_types or query.ban_types_list:
        return [], 0

    if query.is_expired is not None:
        now = get_datetime_utc()
        if query.is_expired:
            filters.append(col(Ban.expires_on).is_not(None))
            filters.append(col(Ban.expires_on) < now)
        else:
            filters.append(
                or_(
                    col(Ban.expires_on).is_(None),
                    col(Ban.expires_on) >= now,
                )
            )

    if query.ip is not None:
        filters.append(col(Ban.ip) == query.ip)
    if query.steamid64 is not None:
        filters.append(col(Ban.steamid64) == query.steamid64)
    if query.notes_contains is not None:
        filters.append(col(Ban.notes).ilike(f"%{query.notes_contains}%"))
    if query.stats_contains is not None:
        filters.append(col(Ban.stats).ilike(f"%{query.stats_contains}%"))
    if query.server_id is not None:
        filters.append(col(Ban.server_id) == query.server_id)
    if query.created_since is not None:
        filters.append(col(Ban.created_on) >= query.created_since)
    if query.updated_since is not None:
        filters.append(col(Ban.updated_on) >= query.updated_since)

    count_statement = select(func.count()).select_from(Ban)
    statement = select(Ban)
    for condition in filters:
        count_statement = count_statement.where(condition)
        statement = statement.where(condition)

    count = (await session.exec(count_statement)).one()
    bans = list(
        (
            await session.exec(
                statement.order_by(col(Ban.id).desc())
                .offset(query.offset)
                .limit(query.limit)
            )
        ).all()
    )
    return bans, count


async def get_ban_by_id(
    *,
    session: AsyncSession,
    ban_id: int,
) -> Ban | None:
    return await session.get(Ban, ban_id)
