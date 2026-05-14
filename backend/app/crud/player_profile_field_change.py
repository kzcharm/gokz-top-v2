from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    PLAYER_PROFILE_FIELD_ACTION_MAP,
    PlayerAction,
    PlayerActionTimestamp,
    PlayerProfileField,
    PlayerProfileFieldStatus,
)

PLAYER_PROFILE_FIELD_CHANGE_COOLDOWN = timedelta(days=30)
_ACTION_TO_PROFILE_FIELD = {
    action: field for field, action in PLAYER_PROFILE_FIELD_ACTION_MAP.items()
}


@dataclass(frozen=True, slots=True)
class PlayerActionTimestampClaim:
    claimed: bool
    recorded_at: datetime | None = None
    next_available_at: datetime | None = None


async def get_player_action_timestamp(
    *,
    session: AsyncSession,
    player_steamid64: int,
    action: PlayerAction,
) -> PlayerActionTimestamp | None:
    statement = select(PlayerActionTimestamp).where(
        col(PlayerActionTimestamp.player_steamid64) == player_steamid64,
        col(PlayerActionTimestamp.action) == action,
    )
    return (await session.exec(statement)).first()


async def get_player_action_timestamps(
    *,
    session: AsyncSession,
    player_steamid64: int,
    actions: Iterable[PlayerAction] | None = None,
) -> dict[PlayerAction, PlayerActionTimestamp]:
    statement = select(PlayerActionTimestamp).where(
        col(PlayerActionTimestamp.player_steamid64) == player_steamid64,
    )
    if actions is not None:
        statement = statement.where(col(PlayerActionTimestamp.action).in_(list(actions)))
    rows = (await session.exec(statement)).all()
    return {row.action: row for row in rows}


async def player_action_timestamp_exists(
    *,
    session: AsyncSession,
    player_steamid64: int,
    action: PlayerAction,
) -> bool:
    statement = select(PlayerActionTimestamp.player_steamid64).where(
        col(PlayerActionTimestamp.player_steamid64) == player_steamid64,
        col(PlayerActionTimestamp.action) == action,
    )
    return (await session.exec(statement)).first() is not None


async def upsert_player_action_timestamp(
    *,
    session: AsyncSession,
    player_steamid64: int,
    action: PlayerAction,
    recorded_at: datetime,
) -> None:
    table = PlayerActionTimestamp.__table__  # type: ignore[attr-defined]
    statement = pg_insert(table).values(
        player_steamid64=player_steamid64,
        action=action,
        recorded_at=recorded_at,
    )
    await session.exec(
        statement.on_conflict_do_update(
            index_elements=[table.c.player_steamid64, table.c.action],
            set_={"recorded_at": recorded_at},
        )
    )


async def claim_player_action_timestamp(
    *,
    session: AsyncSession,
    player_steamid64: int,
    action: PlayerAction,
    recorded_at: datetime,
    cooldown: timedelta,
) -> PlayerActionTimestampClaim:
    stale_before = recorded_at - cooldown
    update_statement = (
        update(PlayerActionTimestamp)
        .where(
            col(PlayerActionTimestamp.player_steamid64) == player_steamid64,
            col(PlayerActionTimestamp.action) == action,
            col(PlayerActionTimestamp.recorded_at) <= stale_before,
        )
        .values(recorded_at=recorded_at)
        .returning(col(PlayerActionTimestamp.recorded_at))
    )
    updated_at = (await session.execute(update_statement)).scalar_one_or_none()
    if updated_at is not None:
        return PlayerActionTimestampClaim(claimed=True, recorded_at=recorded_at)

    table = PlayerActionTimestamp.__table__  # type: ignore[attr-defined]
    insert_statement = (
        pg_insert(table)
        .values(
            player_steamid64=player_steamid64,
            action=action,
            recorded_at=recorded_at,
        )
        .on_conflict_do_nothing(index_elements=[table.c.player_steamid64, table.c.action])
        .returning(table.c.recorded_at)
    )
    inserted_at = (await session.execute(insert_statement)).scalar_one_or_none()
    if inserted_at is not None:
        return PlayerActionTimestampClaim(claimed=True, recorded_at=recorded_at)

    existing = await get_player_action_timestamp(
        session=session,
        player_steamid64=player_steamid64,
        action=action,
    )
    next_available_at = (
        None if existing is None else existing.recorded_at + cooldown
    )
    return PlayerActionTimestampClaim(
        claimed=False,
        recorded_at=existing.recorded_at if existing is not None else None,
        next_available_at=next_available_at,
    )


async def get_player_profile_field_changes(
    *,
    session: AsyncSession,
    player_steamid64: int,
    fields: Iterable[PlayerProfileField] | None = None,
) -> dict[PlayerProfileField, PlayerActionTimestamp]:
    actions = (
        [PLAYER_PROFILE_FIELD_ACTION_MAP[field] for field in fields]
        if fields is not None
        else list(PLAYER_PROFILE_FIELD_ACTION_MAP.values())
    )
    rows = await get_player_action_timestamps(
        session=session,
        player_steamid64=player_steamid64,
        actions=actions,
    )
    return {
        _ACTION_TO_PROFILE_FIELD[action]: row
        for action, row in rows.items()
        if action in _ACTION_TO_PROFILE_FIELD
    }


async def player_profile_field_change_exists(
    *,
    session: AsyncSession,
    player_steamid64: int,
    field: PlayerProfileField,
) -> bool:
    return await player_action_timestamp_exists(
        session=session,
        player_steamid64=player_steamid64,
        action=PLAYER_PROFILE_FIELD_ACTION_MAP[field],
    )


async def upsert_player_profile_field_change(
    *,
    session: AsyncSession,
    player_steamid64: int,
    field: PlayerProfileField,
    changed_at: datetime,
) -> None:
    await upsert_player_action_timestamp(
        session=session,
        player_steamid64=player_steamid64,
        action=PLAYER_PROFILE_FIELD_ACTION_MAP[field],
        recorded_at=changed_at,
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
