import uuid
from datetime import datetime
from typing import Any, cast

from sqlalchemy import and_, exists, func, not_, or_
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.crud.player import get_player_display_name, to_player_ref_public
from app.models import (
    Ban,
    BanCompatPublicV0,
    BanCreate,
    BanListItemPublic,
    BanListQuery,
    BanPublic,
    BanType,
    Player,
)
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
        select(Ban.uuid).where(
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


def not_active_ban_exists_split_clause(
    *,
    steamid64_column: ColumnElement[Any],
    now: datetime | None = None,
) -> ColumnElement[bool]:
    current_time = now or get_datetime_utc()
    return and_(
        ~exists(
            select(Ban.uuid).where(
                col(Ban.steamid64) == steamid64_column,
                col(Ban.expires_on).is_(None),
            )
        ),
        ~exists(
            select(Ban.uuid).where(
                col(Ban.steamid64) == steamid64_column,
                col(Ban.expires_on) >= current_time,
            )
        ),
    )


def to_ban_compat_public_v0(
    *,
    ban: Ban,
    player: Player | None = None,
) -> BanCompatPublicV0:
    if ban.id is None:
        raise ValueError("Compatibility ban payload requires a GlobalAPI id")

    player_name = (
        get_player_display_name(player=player)
        if player is not None
        else str(ban.steamid64)
    )
    return BanCompatPublicV0(
        id=ban.id,
        ban_type=ban.ban_type,
        expires_on=ban.expires_on,
        ip=ban.ip,
        steamid64=str(ban.steamid64),
        player_name=player_name,
        notes=ban.notes,
        stats=ban.stats,
        server_id=ban.server_id,
        updated_by_id=ban.updated_by_id,
        created_on=ban.created_at,
        updated_on=ban.updated_at,
    )


def to_ban_public(*, ban: Ban, player: Player | None = None) -> BanPublic:
    return BanPublic(
        uuid=ban.uuid,
        id=ban.id,
        ban_type=ban.ban_type,
        expires_on=ban.expires_on,
        ip=ban.ip,
        notes=ban.notes,
        stats=ban.stats,
        server_id=ban.server_id,
        updated_by_id=ban.updated_by_id,
        created_on=ban.created_at,
        updated_on=ban.updated_at,
        player=to_player_ref_public(player=player) if player is not None else None,
    )


def to_ban_list_item_public(
    *, ban: Ban, player: Player | None = None
) -> BanListItemPublic:
    return BanListItemPublic(
        uuid=ban.uuid,
        ban_type=ban.ban_type,
        expires_on=ban.expires_on,
        ip=ban.ip,
        notes=ban.notes,
        stats=ban.stats,
        server_id=ban.server_id,
        updated_by_id=ban.updated_by_id,
        created_on=ban.created_at,
        updated_on=ban.updated_at,
        player=to_player_ref_public(player=player) if player is not None else None,
    )


async def read_bans(
    *,
    session: AsyncSession,
    query: BanListQuery,
    external_only: bool = False,
) -> tuple[list[tuple[Ban, Player | None]], int]:
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
        filters.append(col(Ban.created_at) >= query.created_since)
    if query.updated_since is not None:
        filters.append(col(Ban.updated_at) >= query.updated_since)
    if external_only:
        filters.append(col(Ban.id).is_not(None))

    count_statement = select(func.count()).select_from(Ban)
    statement = (
        select(Ban, Player)
        .select_from(Ban)
        .outerjoin(Player, col(Player.steamid64) == col(Ban.steamid64))
    )
    for condition in filters:
        count_statement = count_statement.where(condition)
        statement = statement.where(condition)

    count = (await session.exec(count_statement)).one()
    bans = cast(
        list[tuple[Ban, Player | None]],
        list(
            (
                await session.exec(
                    statement.order_by(
                        col(Ban.created_at).desc(),
                        col(Ban.uuid).desc(),
                    )
                    .offset(query.offset)
                    .limit(query.limit)
                )
            ).all()
        ),
    )
    return bans, count


async def get_ban_by_uuid(
    *,
    session: AsyncSession,
    ban_uuid: uuid.UUID,
) -> tuple[Ban, Player | None] | None:
    statement = (
        select(Ban, Player)
        .select_from(Ban)
        .outerjoin(Player, col(Player.steamid64) == col(Ban.steamid64))
        .where(col(Ban.uuid) == ban_uuid)
    )
    return (await session.exec(statement)).first()


async def create_manual_ban(
    *,
    session: AsyncSession,
    body: BanCreate,
    steamid64: int,
    updated_by_steamid64: int,
) -> Ban:
    now = get_datetime_utc()
    ban = Ban(
        ban_type=body.ban_type,
        expires_on=body.expires_on,
        steamid64=steamid64,
        notes=body.notes,
        stats=body.stats,
        updated_by_id=str(updated_by_steamid64),
        created_at=now,
        updated_at=now,
        synced_at=now,
    )
    session.add(ban)
    await session.commit()
    await session.refresh(ban)
    return ban
