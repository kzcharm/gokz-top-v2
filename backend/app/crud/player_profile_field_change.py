from collections.abc import Iterable
from datetime import datetime, timedelta

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    PlayerProfileField,
    PlayerProfileFieldChange,
    PlayerProfileFieldStatus,
)

PLAYER_PROFILE_FIELD_CHANGE_COOLDOWN = timedelta(days=30)


async def get_player_profile_field_changes(
    *,
    session: AsyncSession,
    player_steamid64: int,
    fields: Iterable[PlayerProfileField] | None = None,
) -> dict[PlayerProfileField, PlayerProfileFieldChange]:
    statement = select(PlayerProfileFieldChange).where(
        col(PlayerProfileFieldChange.player_steamid64) == player_steamid64,
    )
    if fields is not None:
        statement = statement.where(
            col(PlayerProfileFieldChange.field).in_(list(fields))
        )
    rows = (await session.exec(statement)).all()
    return {row.field: row for row in rows}


async def player_profile_field_change_exists(
    *,
    session: AsyncSession,
    player_steamid64: int,
    field: PlayerProfileField,
) -> bool:
    statement = select(PlayerProfileFieldChange.player_steamid64).where(
        col(PlayerProfileFieldChange.player_steamid64) == player_steamid64,
        col(PlayerProfileFieldChange.field) == field,
    )
    return (await session.exec(statement)).first() is not None


async def upsert_player_profile_field_change(
    *,
    session: AsyncSession,
    player_steamid64: int,
    field: PlayerProfileField,
    changed_at: datetime,
) -> None:
    table = PlayerProfileFieldChange.__table__  # type: ignore[attr-defined]
    statement = pg_insert(table).values(
        player_steamid64=player_steamid64,
        field=field,
        changed_at=changed_at,
    )
    await session.exec(
        statement.on_conflict_do_update(
            index_elements=[table.c.player_steamid64, table.c.field],
            set_={"changed_at": changed_at},
        )
    )


def build_player_profile_field_status(
    *,
    changed_at: datetime | None,
    now: datetime,
    cooldown: timedelta = PLAYER_PROFILE_FIELD_CHANGE_COOLDOWN,
) -> PlayerProfileFieldStatus:
    if changed_at is None:
        return PlayerProfileFieldStatus()

    next_available_at = changed_at + cooldown
    can_change = next_available_at <= now
    return PlayerProfileFieldStatus(
        last_changed_at=changed_at,
        next_available_at=None if can_change else next_available_at,
        can_change=can_change,
    )
