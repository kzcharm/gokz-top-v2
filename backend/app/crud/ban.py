import uuid
from datetime import datetime
from typing import Any, cast

from sqlalchemy import and_, exists, func, not_, or_
from sqlalchemy.orm import aliased
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
    BanUpdate,
    BanType,
    Player,
)
from app.models.utils import get_datetime_utc

type BanReadRow = tuple[Ban, Player | None, Player | None]


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
                col(Ban.expires_at).is_(None),
                col(Ban.expires_at) >= current_time,
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
                col(Ban.expires_at).is_(None),
            )
        ),
        ~exists(
            select(Ban.uuid).where(
                col(Ban.steamid64) == steamid64_column,
                col(Ban.expires_at) >= current_time,
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
        expires_on=ban.expires_at,
        ip=ban.ip,
        steamid64=str(ban.steamid64),
        player_name=player_name,
        notes=ban.notes,
        stats=ban.stats,
        server_id=ban.server_id,
        updated_by_id=(
            str(ban.updated_by_steamid64)
            if ban.updated_by_steamid64 is not None
            else None
        ),
        created_on=ban.created_at,
        updated_on=ban.updated_at,
    )


def to_ban_public(
    *,
    ban: Ban,
    player: Player | None = None,
    updated_by_player: Player | None = None,
    include_admin_fields: bool = False,
) -> BanPublic:
    payload: dict[str, Any] = {
        "uuid": ban.uuid,
        "id": ban.id,
        "ban_type": ban.ban_type,
        "expires_at": ban.expires_at,
        "ip": ban.ip,
        "notes": ban.notes,
        "stats": ban.stats,
        "server_id": ban.server_id,
        "created_at": ban.created_at,
        "updated_at": ban.updated_at,
        "player": to_player_ref_public(player=player) if player is not None else None,
    }
    if include_admin_fields:
        payload["updated_by_steamid64"] = (
            str(ban.updated_by_steamid64)
            if ban.updated_by_steamid64 is not None
            else None
        )
        payload["updated_by_player"] = (
            to_player_ref_public(player=updated_by_player)
            if updated_by_player is not None
            else None
        )

    return BanPublic(**payload)


def to_ban_list_item_public(
    *,
    ban: Ban,
    player: Player | None = None,
    updated_by_player: Player | None = None,
    include_admin_fields: bool = False,
) -> BanListItemPublic:
    payload: dict[str, Any] = {
        "uuid": ban.uuid,
        "ban_type": ban.ban_type,
        "expires_at": ban.expires_at,
        "ip": ban.ip,
        "notes": ban.notes,
        "stats": ban.stats,
        "server_id": ban.server_id,
        "created_at": ban.created_at,
        "updated_at": ban.updated_at,
        "player": to_player_ref_public(player=player) if player is not None else None,
    }
    if include_admin_fields:
        payload["updated_by_steamid64"] = (
            str(ban.updated_by_steamid64)
            if ban.updated_by_steamid64 is not None
            else None
        )
        payload["updated_by_player"] = (
            to_player_ref_public(player=updated_by_player)
            if updated_by_player is not None
            else None
        )

    return BanListItemPublic(**payload)


async def read_bans(
    *,
    session: AsyncSession,
    query: BanListQuery,
    external_only: bool = False,
) -> tuple[list[BanReadRow], int]:
    updated_by_player = aliased(Player)
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
            filters.append(col(Ban.expires_at).is_not(None))
            filters.append(col(Ban.expires_at) < now)
        else:
            filters.append(
                or_(
                    col(Ban.expires_at).is_(None),
                    col(Ban.expires_at) >= now,
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
        select(Ban, Player, updated_by_player)
        .select_from(Ban)
        .outerjoin(Player, col(Player.steamid64) == col(Ban.steamid64))
        .outerjoin(
            updated_by_player,
            col(updated_by_player.steamid64) == col(Ban.updated_by_steamid64),
        )
    )
    for condition in filters:
        count_statement = count_statement.where(condition)
        statement = statement.where(condition)

    count = (await session.exec(count_statement)).one()
    bans = cast(
        list[BanReadRow],
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
) -> BanReadRow | None:
    updated_by_player = aliased(Player)
    statement = (
        select(Ban, Player, updated_by_player)
        .select_from(Ban)
        .outerjoin(Player, col(Player.steamid64) == col(Ban.steamid64))
        .outerjoin(
            updated_by_player,
            col(updated_by_player.steamid64) == col(Ban.updated_by_steamid64),
        )
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
        expires_at=body.expires_at,
        steamid64=steamid64,
        notes=body.notes,
        stats=body.stats,
        updated_by_steamid64=updated_by_steamid64,
        created_at=now,
        updated_at=now,
        synced_at=now,
    )
    session.add(ban)
    await session.commit()
    await session.refresh(ban)
    return ban


async def update_ban(
    *,
    session: AsyncSession,
    ban: Ban,
    body: BanUpdate,
    updated_by_steamid64: int,
) -> Ban:
    ban.ban_type = body.ban_type
    ban.expires_at = body.expires_at
    ban.notes = body.notes
    ban.updated_by_steamid64 = updated_by_steamid64
    ban.updated_at = get_datetime_utc()
    session.add(ban)
    await session.commit()
    await session.refresh(ban)
    return ban
