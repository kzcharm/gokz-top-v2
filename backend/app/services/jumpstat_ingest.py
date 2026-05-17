from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    Jumpstat,
    Player,
    PlayerAction,
    PlayerActionTimestamp,
    ServerGroup,
    generate_uuid7,
)
from app.services.geoip import GeoIPLocation
from app.services.jump_replay_parser import ParsedJumpReplay, parse_jump_replay_bytes
from app.services.jump_replay_storage import save_jump_replay


@dataclass(frozen=True)
class IngestJumpReplayResult:
    jumpstat: Jumpstat
    created: bool


async def _ensure_placeholder_player(
    *,
    session: AsyncSession,
    steamid64: int,
    now: datetime,
    location: GeoIPLocation | None = None,
) -> None:
    country = location.country_code if location is not None else None
    player_table = Player.__table__  # type: ignore[attr-defined]
    field_change_table = PlayerActionTimestamp.__table__  # type: ignore[attr-defined]
    insert_statement = pg_insert(player_table).values(
        steamid64=steamid64,
        name=str(steamid64),
        country=country,
        created_at=now,
        updated_at=now,
    )

    if country is None:
        await session.exec(insert_statement.on_conflict_do_nothing())
        return

    await session.exec(
        insert_statement.on_conflict_do_update(
            index_elements=[player_table.c.steamid64],
            set_={"country": country, "updated_at": now},
            where=~select(field_change_table.c.player_steamid64)
            .where(
                field_change_table.c.player_steamid64 == player_table.c.steamid64,
                field_change_table.c.action == PlayerAction.COUNTRY_MANUAL_OVERRIDE,
            )
            .exists(),
        )
    )


async def find_jumpstat_by_signature(
    *,
    session: AsyncSession,
    server_group_id: uuid.UUID,
    replay: ParsedJumpReplay,
) -> Jumpstat | None:
    statement = select(Jumpstat).where(
        col(Jumpstat.player_steamid64) == replay.steamid64,
        col(Jumpstat.server_group_id) == server_group_id,
        col(Jumpstat.jumped_at) == replay.jumped_at,
        col(Jumpstat.mode) == replay.mode,
        col(Jumpstat.type) == replay.type,
        col(Jumpstat.block) == replay.block,
        col(Jumpstat.distance) == replay.distance,
        col(Jumpstat.pre_speed) == replay.pre_speed,
        col(Jumpstat.max_speed) == replay.max_speed,
        col(Jumpstat.strafes) == replay.strafes,
    )
    return (await session.exec(statement)).first()


def build_jumpstat_from_replay(
    *,
    jumpstat_id: uuid.UUID,
    server_group_id: uuid.UUID,
    replay: ParsedJumpReplay,
) -> Jumpstat:
    return Jumpstat(
        id=jumpstat_id,
        player_steamid64=replay.steamid64,
        server_group_id=server_group_id,
        mode=replay.mode,
        type=replay.type,
        distance=replay.distance,
        block=replay.block,
        strafes=replay.strafes,
        sync_percent=replay.sync_percent,
        pre_speed=replay.pre_speed,
        max_speed=replay.max_speed,
        w_count=replay.w_count,
        overlap_count=replay.overlap_count,
        dead_air_count=replay.dead_air_count,
        width=replay.width,
        height=replay.height,
        airtime_percent=replay.airtime_percent,
        offset=replay.offset,
        crouched_ticks=replay.crouched_ticks,
        edge=None,
        deviation=replay.deviation,
        strafe_stats=replay.strafe_stats,
        jumped_at=replay.jumped_at,
        created_at=replay.jumped_at,
        updated_at=replay.jumped_at,
    )


async def ingest_jump_replay(
    *,
    session: AsyncSession,
    group: ServerGroup,
    replay_bytes: bytes,
    source_name: str,
) -> IngestJumpReplayResult:
    parsed = parse_jump_replay_bytes(data=replay_bytes, source_name=source_name)
    await _ensure_placeholder_player(
        session=session,
        steamid64=parsed.steamid64,
        now=parsed.jumped_at,
    )
    jumpstat = build_jumpstat_from_replay(
        jumpstat_id=generate_uuid7(timestamp=parsed.jumped_at),
        server_group_id=group.id,
        replay=parsed,
    )
    session.add(jumpstat)
    await session.commit()
    save_jump_replay(jumpstat_id=jumpstat.id, replay_bytes=replay_bytes)
    await session.refresh(jumpstat)
    return IngestJumpReplayResult(jumpstat=jumpstat, created=True)


async def import_jump_replay(
    *,
    session: AsyncSession,
    group: ServerGroup,
    replay_bytes: bytes,
    source_name: str,
) -> IngestJumpReplayResult:
    parsed = parse_jump_replay_bytes(data=replay_bytes, source_name=source_name)
    await _ensure_placeholder_player(
        session=session,
        steamid64=parsed.steamid64,
        now=parsed.jumped_at,
    )

    existing = await find_jumpstat_by_signature(
        session=session,
        server_group_id=group.id,
        replay=parsed,
    )
    if existing is not None:
        save_jump_replay(jumpstat_id=existing.id, replay_bytes=replay_bytes)
        return IngestJumpReplayResult(jumpstat=existing, created=False)

    jumpstat = build_jumpstat_from_replay(
        jumpstat_id=generate_uuid7(timestamp=parsed.jumped_at),
        server_group_id=group.id,
        replay=parsed,
    )
    session.add(jumpstat)
    await session.commit()
    save_jump_replay(jumpstat_id=jumpstat.id, replay_bytes=replay_bytes)
    await session.refresh(jumpstat)
    return IngestJumpReplayResult(jumpstat=jumpstat, created=True)
