"""Replay availability is database metadata; storage is touched only by writers."""

import hashlib
import uuid
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.crud.ban import not_active_ban_exists_clause
from app.models import Map, Record, RecordReplay, ReplayListQuery
from app.models.utils import get_datetime_utc


async def available_record_uuids(
    session: AsyncSession, record_uuids: Sequence[uuid.UUID]
) -> set[uuid.UUID]:
    if not record_uuids:
        return set()
    return set(
        (
            await session.exec(
                select(RecordReplay.record_uuid).where(
                    col(RecordReplay.record_uuid).in_(record_uuids),
                    col(RecordReplay.available).is_(True),
                )
            )
        ).all()
    )


async def list_replays(
    session: AsyncSession, query: ReplayListQuery
) -> tuple[list[uuid.UUID], int]:
    statement = (
        select(Record.uuid)
        .join(RecordReplay)
        .join(Map)
        .where(
            col(RecordReplay.available).is_(True),
            col(Record.is_valid).is_(True),
            col(Record.stage) == query.stage,
        )
    )
    if query.map_name is not None:
        statement = statement.where(col(Map.name) == query.map_name)
    if query.steamid64 is not None:
        statement = statement.where(col(Record.steamid64) == query.steamid64)
    if query.mode is not None:
        statement = statement.where(col(Record.mode) == query.mode)
    if query.teleports is not None:
        statement = statement.where(col(Record.teleports) == query.teleports)
    if query.exclude_cheaters:
        statement = statement.where(
            not_active_ban_exists_clause(steamid64_column=col(Record.steamid64))
        )
    count = (
        await session.exec(select(func.count()).select_from(statement.subquery()))
    ).one()
    ids = (
        await session.exec(
            statement.order_by(col(Record.time), col(Record.uuid))
            .offset(query.offset)
            .limit(query.limit)
        )
    ).all()
    return list(ids), count


async def register_disk_replay(
    session: AsyncSession, record_uuid: uuid.UUID, path: Path
) -> None:
    data = path.read_bytes()
    checksum = hashlib.sha256(data).hexdigest()
    entry = await session.get(RecordReplay, record_uuid)
    if entry is not None and entry.checksum != checksum:
        raise ValueError("A different replay is already registered for this record")
    if entry is None:
        entry = RecordReplay(
            record_uuid=record_uuid,
            storage="disk",
            key=str(path.resolve()),
            checksum=checksum,
            size=len(data),
        )
    entry.available = True
    entry.checked_at = get_datetime_utc()
    session.add(entry)
    await session.flush()
    record = await session.get(Record, record_uuid)
    if record is not None:
        await session.refresh(record, attribute_names=["replay_available"])
    from app.crud.record import notify_recent_record_updated

    await notify_recent_record_updated(session=session, record_uuid=record_uuid)
