import gzip
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.importers.records_archive import import_records_from_path, iter_record_payloads
from app.models import Player

pytestmark = pytest.mark.asyncio


def _bind_import_session(
    monkeypatch: pytest.MonkeyPatch,
    db: AsyncSession,
) -> None:
    @asynccontextmanager
    async def _session_maker():
        yield db

    monkeypatch.setattr(
        "app.importers.records_archive.async_session_maker", _session_maker
    )


def _build_payload(
    *,
    record_id: int,
    steamid64: int,
    map_id: int = 980200,
    server_id: int = 980300,
    player_name: str = "Runner",
    map_name: str = "kz_payload_map",
    server_name: str = "Payload Server",
    points: int = 500,
    is_valid: bool = True,
    created_on: str = "2026-03-30T12:34:56",
    updated_on: str = "2026-03-30T12:35:56",
) -> dict[str, object]:
    return {
        "id": record_id,
        "steamid64": str(steamid64),
        "player_name": player_name,
        "server_id": server_id,
        "server_name": server_name,
        "map_id": map_id,
        "map_name": map_name,
        "stage": 0,
        "mode": "kz_timer",
        "tickrate": 128,
        "time": 45.678,
        "teleports": 0,
        "points": points,
        "created_on": created_on,
        "updated_on": updated_on,
        "updated_by": str(steamid64),
        "replay_id": 321,
        "is_valid": is_valid,
    }


def test_iter_record_payloads_reads_json_and_gzip_archives(tmp_path) -> None:
    payloads = [
        _build_payload(record_id=998200, steamid64=76561198000000001),
        _build_payload(record_id=998201, steamid64=76561198000000002),
    ]

    json_path = tmp_path / "records.json"
    json_path.write_text(json.dumps(payloads), encoding="utf-8")

    gzip_path = tmp_path / "records.json.gz"
    with gzip.open(gzip_path, mode="wt", encoding="utf-8") as stream:
        json.dump(payloads, stream)

    assert list(iter_record_payloads(json_path)) == payloads
    assert list(iter_record_payloads(gzip_path)) == payloads


async def test_import_records_from_path_creates_records_and_uses_created_on_for_uuid(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _bind_import_session(monkeypatch, db)
    steamid64 = 76561198000000011
    archive_path = tmp_path / "records.json.gz"
    payload = _build_payload(
        record_id=998210,
        steamid64=steamid64,
        is_valid=False,
        created_on="2026-03-30T12:34:56",
    )
    with gzip.open(archive_path, mode="wt", encoding="utf-8") as stream:
        json.dump([payload], stream)

    result = await import_records_from_path(archive_path, batch_size=1, log_every=1)

    assert result.read == 1
    assert result.processed == 1
    assert result.created == 1
    assert result.updated == 0
    assert result.errors == 0

    record = await crud.get_record_by_id(session=db, record_id=998210)
    assert record is not None
    assert record.is_valid is False
    assert record.uuid.version == 7
    expected_created_on = datetime(2026, 3, 30, 12, 34, 56, tzinfo=UTC)
    assert record.uuid.time == int(expected_created_on.timestamp() * 1000)

    player = await db.get(Player, steamid64)
    assert player is not None
    assert player.name == "Runner"
    assert player.created_at == expected_created_on
    assert player.last_played_at == expected_created_on


async def test_import_records_from_path_updates_existing_record_without_changing_uuid(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _bind_import_session(monkeypatch, db)
    steamid64 = 76561198000000012
    original_payload = _build_payload(
        record_id=998220,
        steamid64=steamid64,
        points=100,
        is_valid=False,
        created_on="2026-03-30T12:00:00",
        updated_on="2026-03-30T12:00:00",
    )
    updated_payload = _build_payload(
        record_id=998220,
        steamid64=steamid64,
        points=900,
        is_valid=True,
        created_on="2026-03-30T12:00:00",
        updated_on="2026-03-30T13:00:00",
    )

    archive_path = tmp_path / "records.json"
    archive_path.write_text(json.dumps([original_payload]), encoding="utf-8")
    await import_records_from_path(archive_path, batch_size=1, log_every=1)

    existing = await crud.get_record_by_id(session=db, record_id=998220)
    assert existing is not None
    existing_uuid = existing.uuid

    archive_path.write_text(json.dumps([updated_payload]), encoding="utf-8")
    result = await import_records_from_path(archive_path, batch_size=1, log_every=1)

    assert result.read == 1
    assert result.processed == 1
    assert result.created == 0
    assert result.updated == 1
    assert result.errors == 0

    db.expire_all()
    refreshed = await crud.get_record_by_id(session=db, record_id=998220)
    assert refreshed is not None
    assert refreshed.uuid == existing_uuid
    assert refreshed.points == 900
    assert refreshed.is_valid is True


async def test_import_records_from_path_skips_records_with_null_id(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _bind_import_session(monkeypatch, db)
    steamid64 = 76561198000000013
    archive_path = tmp_path / "records-null-id.json"
    payload = _build_payload(record_id=998230, steamid64=steamid64)
    payload["id"] = None
    archive_path.write_text(json.dumps([payload]), encoding="utf-8")

    result = await import_records_from_path(archive_path, batch_size=1, log_every=1)

    assert result.read == 1
    assert result.processed == 0
    assert result.created == 0
    assert result.updated == 0
    assert result.errors == 1

    player = await db.get(Player, steamid64)
    assert player is None
