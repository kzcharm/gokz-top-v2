"""Record transfers retain auditable ownership changes and honor date filters."""

import hashlib
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Ban, BanType, KZMode, Map, Player, Record, ServerGlobalapi
from app.tasks import record_transfer as transfer
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("dry_run", [False, True])
async def test_transfer_writes_audit_and_preserves_unselected_runs(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    dry_run: bool,
) -> None:
    @asynccontextmanager
    async def session_factory():
        yield db

    monkeypatch.setattr(transfer, "async_session_maker", session_factory)
    monkeypatch.setattr(transfer.rating_task, "async_session_maker", session_factory)
    source, target = random_steamid64(), random_steamid64()
    db.add_all(
        [
            Player(steamid64=source, name="Transfer source"),
            Player(steamid64=target, name="Transfer target"),
            Map(id=972400, name="kz_transfer_quality", validated=True),
            ServerGlobalapi(id=972400, name="Transfer server"),
        ]
    )
    await db.flush()
    records = [
        Record(
            steamid64=source,
            server_id=972400,
            mode=KZMode.KZT,
            map_id=972400,
            time=Decimal(str(50 - index)),
            created_at=datetime(2025, 1, index + 1, tzinfo=UTC),
        )
        for index in range(2)
    ]
    db.add_all(records)
    await db.commit()
    selected_uuid = records[1].uuid
    result = await transfer.transfer_records(
        source_steamid64=source,
        target_steamid64=target,
        audit_path=tmp_path / "audit.jsonl",
        after="2025-01-02",
        before="2025-01-02",
        dry_run=dry_run,
    )
    assert result.transferred_records == 1
    assert result.source_records_before == 2 and result.target_records_before == 0
    assert result.source_records_after == (2 if dry_run else 1)
    assert result.target_records_after == (0 if dry_run else 1)
    audit = result.audit_path.read_bytes()
    assert hashlib.sha256(audit).hexdigest() == result.checksum
    payload = json.loads(audit)
    assert payload["record_uuid"] == str(selected_uuid)
    assert payload["old_steamid64"] == str(source)
    assert payload["new_steamid64"] == str(target)
    assert json.loads(result.summary_path.read_text())["record_count"] == 1
    selected = await db.get(Record, selected_uuid)
    assert selected.steamid64 == (source if dry_run else target)
    assert (await db.exec(select(Record).where(Record.steamid64 == source))).all()
    with pytest.raises(RuntimeError, match="Audit file already exists"):
        transfer._write_audit_files(
            audit_path=result.audit_path,
            records=[],
            source_steamid64=source,
            target_steamid64=target,
            dry_run=dry_run,
        )


async def test_transfer_refuses_missing_players_and_mirrored_bans(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    @asynccontextmanager
    async def session_factory():
        yield db

    monkeypatch.setattr(transfer, "async_session_maker", session_factory)
    source, target = random_steamid64(), random_steamid64()
    with pytest.raises(RuntimeError, match="Player does not exist"):
        await transfer.transfer_records(
            source_steamid64=source,
            target_steamid64=target,
            audit_path=tmp_path / "missing.jsonl",
            dry_run=True,
        )
    db.add_all(
        [
            Player(steamid64=source, name="Source"),
            Player(steamid64=target, name="Target"),
        ]
    )
    await db.flush()
    with pytest.raises(RuntimeError, match="No source records"):
        await transfer.transfer_records(
            source_steamid64=source,
            target_steamid64=target,
            audit_path=tmp_path / "empty.jsonl",
            dry_run=True,
        )
    db.add(Ban(id=972400, steamid64=target, ban_type=BanType.OTHER))
    await db.flush()
    with pytest.raises(RuntimeError, match="active mirrored ban"):
        await transfer.transfer_records(
            source_steamid64=source,
            target_steamid64=target,
            audit_path=tmp_path / "banned.jsonl",
            dry_run=True,
        )
    assert not list(tmp_path.glob("*.jsonl"))
    assert await transfer._load_course_ids_by_record_key(session=db, records=[]) == {}
    with pytest.raises(ValueError, match="after must be earlier"):
        await transfer.transfer_records(
            after="2025-02-01", before="2025-01-01", dry_run=True
        )
    assert transfer.parse_datetime_boundary(None) is None
    assert transfer.parse_datetime_boundary("2025-01-01T02:00:00+02:00") == datetime(
        2025, 1, 1, tzinfo=UTC
    )
    assert ".temp/record-transfers" in str(transfer.default_audit_path())
