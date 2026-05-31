from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, case, or_
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import (
    Jumpstat,
    JumpstatReplayEligibilityPublic,
    JumpstatType,
    KZMode,
    get_datetime_utc,
)
from app.services.jump_replay_storage import delete_jump_replay, get_jump_replay_path

LONG_JUMP_REPLAY_KEEP_LIMIT = 10
DEFAULT_JUMP_REPLAY_KEEP_LIMIT = 1
RETAINABLE_JUMPSTAT_TYPES = (
    JumpstatType.LJ,
    JumpstatType.BH,
    JumpstatType.MBH,
    JumpstatType.WJ,
    JumpstatType.LAJ,
    JumpstatType.LAH,
    JumpstatType.JB,
    JumpstatType.LBH,
    JumpstatType.LWJ,
)


@dataclass(frozen=True, slots=True)
class JumpReplayCleanupResult:
    checked: int
    deleted: int
    missing: int
    errors: int


def get_jump_replay_keep_limit(jump_type: JumpstatType) -> int:
    if jump_type == JumpstatType.LJ:
        return LONG_JUMP_REPLAY_KEEP_LIMIT
    if jump_type in RETAINABLE_JUMPSTAT_TYPES:
        return DEFAULT_JUMP_REPLAY_KEEP_LIMIT
    return 0


async def get_jump_replay_eligibility(
    *,
    session: AsyncSession,
    player_steamid64: int,
    mode: KZMode,
    jump_type: JumpstatType,
    distance: Decimal,
    jumped_at: datetime | None = None,
) -> JumpstatReplayEligibilityPublic:
    keep_limit = get_jump_replay_keep_limit(jump_type)
    if keep_limit == 0:
        return JumpstatReplayEligibilityPublic(
            eligible=False,
            keep_limit=0,
        )

    filters: list[ColumnElement[bool]] = [
        col(Jumpstat.player_steamid64) == player_steamid64,
        col(Jumpstat.mode) == mode,
        col(Jumpstat.type) == jump_type,
    ]
    better_conditions: list[ColumnElement[bool]] = [
        and_(*filters, col(Jumpstat.distance) > distance)
    ]
    if jumped_at is not None:
        better_conditions.append(
            and_(
                *filters,
                col(Jumpstat.distance) == distance,
                col(Jumpstat.jumped_at) > jumped_at,
            )
        )

    better_count = int(
        (
            await session.exec(
                select(func.count()).select_from(Jumpstat).where(or_(*better_conditions))
            )
        ).one()
    )
    rank = better_count + 1

    cutoff = (
        await session.exec(
            select(col(Jumpstat.distance), col(Jumpstat.jumped_at))
            .where(*filters)
            .order_by(
                col(Jumpstat.distance).desc(),
                col(Jumpstat.jumped_at).desc(),
                col(Jumpstat.id).desc(),
            )
            .offset(keep_limit - 1)
            .limit(1)
        )
    ).first()

    cutoff_distance: float | None = None
    cutoff_jumped_at: datetime | None = None
    if cutoff is not None:
        cutoff_distance = float(cutoff[0])
        cutoff_jumped_at = cutoff[1]

    return JumpstatReplayEligibilityPublic(
        eligible=rank <= keep_limit,
        keep_limit=keep_limit,
        rank=rank,
        cutoff_distance=cutoff_distance,
        cutoff_jumped_at=cutoff_jumped_at,
    )


async def is_parsed_jump_replay_eligible(
    *,
    session: AsyncSession,
    player_steamid64: int,
    mode: KZMode,
    jump_type: JumpstatType,
    distance: Decimal,
    jumped_at: datetime,
) -> bool:
    eligibility = await get_jump_replay_eligibility(
        session=session,
        player_steamid64=player_steamid64,
        mode=mode,
        jump_type=jump_type,
        distance=distance,
        jumped_at=jumped_at,
    )
    return eligibility.eligible


async def list_jump_replay_cleanup_candidates(
    *,
    session: AsyncSession,
    now: datetime | None = None,
    older_than: timedelta | None = None,
) -> list[uuid.UUID]:
    cutoff = (now or get_datetime_utc()) - (
        older_than
        or timedelta(days=settings.JUMP_REPLAY_CLEANUP_GRACE_DAYS)
    )
    ranked_jumpstats = (
        select(
            col(Jumpstat.id).label("id"),
            col(Jumpstat.type).label("type"),
            col(Jumpstat.jumped_at).label("jumped_at"),
            func.row_number()
            .over(
                partition_by=(
                    col(Jumpstat.player_steamid64),
                    col(Jumpstat.mode),
                    col(Jumpstat.type),
                ),
                order_by=(
                    col(Jumpstat.distance).desc(),
                    col(Jumpstat.jumped_at).desc(),
                    col(Jumpstat.id).desc(),
                ),
            )
            .label("replay_rank"),
        )
        .where(col(Jumpstat.type).in_(list(RETAINABLE_JUMPSTAT_TYPES)))
        .subquery()
    )
    keep_limit = case(
        (ranked_jumpstats.c.type == JumpstatType.LJ, LONG_JUMP_REPLAY_KEEP_LIMIT),
        else_=DEFAULT_JUMP_REPLAY_KEEP_LIMIT,
    )
    rows = (
        await session.exec(
            select(ranked_jumpstats.c.id)
            .where(
                ranked_jumpstats.c.jumped_at < cutoff,
                ranked_jumpstats.c.replay_rank > keep_limit,
            )
            .order_by(ranked_jumpstats.c.jumped_at.asc(), ranked_jumpstats.c.id.asc())
        )
    ).all()
    return [uuid.UUID(str(row)) for row in rows]


async def cleanup_old_unkept_jump_replays_once(
    *,
    session: AsyncSession,
    now: datetime | None = None,
    older_than: timedelta | None = None,
) -> JumpReplayCleanupResult:
    candidates = await list_jump_replay_cleanup_candidates(
        session=session,
        now=now,
        older_than=older_than,
    )
    deleted = 0
    missing = 0
    errors = 0
    for jumpstat_id in candidates:
        replay_path = get_jump_replay_path(jumpstat_id=jumpstat_id)
        if not replay_path.exists():
            missing += 1
            continue
        try:
            if delete_jump_replay(jumpstat_id=jumpstat_id):
                deleted += 1
        except OSError:
            errors += 1

    return JumpReplayCleanupResult(
        checked=len(candidates),
        deleted=deleted,
        missing=missing,
        errors=errors,
    )
