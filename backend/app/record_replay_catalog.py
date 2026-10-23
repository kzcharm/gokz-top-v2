"""Explicit bounded catalog backfill/reconciliation; never scheduled automatically."""

import argparse
import asyncio
import logging
import uuid
from pathlib import Path

import httpx
from sqlmodel import col, select

from app.core.db import async_session_maker
from app.crud.record import notify_recent_record_updated
from app.models import Map, Record, RecordReplay, RecordUuidAlias, get_datetime_utc
from app.services import r2_storage
from app.services.record_replay_catalog import register_disk_replay
from app.services.run_replay_storage import get_run_replay_path


async def run(
    action: str, limit: int, after: uuid.UUID | None, record_id: uuid.UUID | None
) -> None:
    async with async_session_maker() as session:
        if record_id:
            alias = await session.get(RecordUuidAlias, record_id)
            if alias:
                record_id = alias.record_uuid
        statement = select(Record).order_by(col(Record.uuid)).limit(limit)
        if after:
            statement = statement.where(col(Record.uuid) > after)
        if record_id:
            statement = statement.where(Record.uuid == record_id)
        for record in (await session.exec(statement)).all():
            entry = await session.get(RecordReplay, record.uuid)
            if action == "backfill" and entry is None:
                map_obj = await session.get(Map, record.map_id)
                if map_obj:
                    path = get_run_replay_path(
                        map_name=map_obj.name, replay_id=record.uuid
                    )
                    if path.is_file():
                        await register_disk_replay(session, record.uuid, path)
            elif action == "reconcile" and entry:
                if entry.storage == "disk":
                    entry.available = Path(entry.key).is_file()
                else:
                    async with httpx.AsyncClient(timeout=30) as client:
                        response = await client.head(
                            r2_storage.build_public_url(entry.key)
                        )
                        if response.status_code == 404:
                            entry.available = False
                        else:
                            response.raise_for_status()
                            entry.available = True
                entry.checked_at = get_datetime_utc()
                session.add(entry)
                await notify_recent_record_updated(
                    session=session, record_uuid=record.uuid
                )
            await session.commit()
            logging.warning("cursor=%s", record.uuid)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["backfill", "reconcile"])
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--after", type=uuid.UUID)
    parser.add_argument("--record", type=uuid.UUID)
    args = parser.parse_args()
    if not 1 <= args.limit <= 10000:
        parser.error("--limit must be between 1 and 10000")
    asyncio.run(run(args.action, args.limit, args.after, args.record))


if __name__ == "__main__":
    main()
