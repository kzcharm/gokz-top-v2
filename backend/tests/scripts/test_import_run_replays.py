import zipfile
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from decimal import Decimal

import py7zr
import pytest
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.importers.run_replays import import_run_replays_from_paths
from app.models import Map, Player, Record, RecordPb, ServerGlobalapi
from app.services.run_replay_storage import get_run_replay_path
from tests.utils.run_replay import build_synthetic_run_replay

pytestmark = pytest.mark.asyncio


def _bind_import_session(
    monkeypatch: pytest.MonkeyPatch,
    db: AsyncSession,
) -> None:
    @asynccontextmanager
    async def _session_maker():
        yield db

    monkeypatch.setattr("app.importers.run_replays.async_session_maker", _session_maker)


async def _create_player(db: AsyncSession, *, steamid64: int, name: str) -> None:
    await db.exec(delete(Player).where(Player.steamid64 == steamid64))
    await db.commit()
    db.add(Player(steamid64=steamid64, name=name))
    await db.commit()


async def _create_map(db: AsyncSession, *, id: int, name: str) -> None:
    await db.exec(delete(Map).where(Map.id == id))
    await db.commit()
    db.add(
        Map(
            id=id,
            name=name,
            filesize=1,
            validated=True,
            difficulty=4,
            approved_by_steamid64=76561198003275951,
        )
    )
    await db.commit()


async def _create_server(db: AsyncSession, *, id: int, name: str) -> None:
    await db.exec(delete(ServerGlobalapi).where(ServerGlobalapi.id == id))
    await db.commit()
    for steamid64 in (76561198000000010, 76561198000000020):

        if await db.get(Player, steamid64) is None:

            db.add(Player(steamid64=steamid64, name=str(steamid64)))

    db.add(

        ServerGlobalapi(
            id=id,
            port=27015,
            ip=f"203.0.113.{id % 255}",
            name=name,
            owner_steamid64=76561198000000010,
            approval_status=1,
            approved_by_steamid64=76561198000000020,
        )
    )
    await db.commit()


async def _create_record(
    db: AsyncSession,
    *,
    id: int,
    steamid64: int,
    map_id: int,
    mode_id: int,
    stage: int,
    time_seconds: Decimal,
    created_on: datetime,
) -> Record:
    record_uuid_subquery = select(Record.uuid).where(Record.id == id)
    await db.exec(delete(RecordPb).where(RecordPb.record_uuid.in_(record_uuid_subquery)))
    await db.exec(delete(Record).where(Record.id == id))
    await db.commit()
    record, _created, _updated = await crud.upsert_record(
        session=db,
        record_id=id,
        record_uuid=None,
        steamid64=steamid64,
        server_id=991000,
        mode_id=mode_id,
        map_id=map_id,
        stage=stage,
        time_seconds=time_seconds,
        teleports=0,
        points=0,
        created_on=created_on,
        updated_on=created_on,
        updated_by=steamid64,
        replay_id=None,
        is_valid=True,
    )
    await db.commit()
    await db.refresh(record)
    return record


async def _seed_dependencies(
    db: AsyncSession,
    *,
    steamid64: int,
    map_name: str = "kz_import_map",
) -> None:
    await _create_player(db, steamid64=steamid64, name="Import Runner")
    await _create_map(db, id=990000, name=map_name)
    await _create_server(db, id=991000, name="Import Server")


async def test_import_run_replays_from_replay_file_creates_replay_file(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _bind_import_session(monkeypatch, db)
    monkeypatch.setattr(settings, "REPLAY_STORAGE_DIR", tmp_path)
    synthetic = build_synthetic_run_replay(map_name="kz_import_map")
    await _seed_dependencies(db, steamid64=synthetic.steamid64)
    record = await _create_record(
        db,
        id=992000,
        steamid64=synthetic.steamid64,
        map_id=990000,
        mode_id=200,
        stage=0,
        time_seconds=Decimal("35.289"),
        created_on=synthetic.recorded_at + timedelta(hours=1),
    )
    replay_path = tmp_path / "single.replay"
    replay_path.write_bytes(synthetic.replay_bytes)

    result = await import_run_replays_from_paths([replay_path])

    assert result.scanned == 1
    assert result.matched == 1
    assert result.imported == 1
    assert result.failed == 0
    assert get_run_replay_path(
        map_name="kz_import_map",
        replay_id=record.uuid,
    ).read_bytes() == synthetic.replay_bytes


async def test_import_run_replays_from_directory_supports_dry_run(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _bind_import_session(monkeypatch, db)
    monkeypatch.setattr(settings, "REPLAY_STORAGE_DIR", tmp_path / "storage")
    synthetic = build_synthetic_run_replay(map_name="kz_dry_run")
    await _seed_dependencies(db, steamid64=synthetic.steamid64, map_name="kz_dry_run")
    record = await _create_record(
        db,
        id=992001,
        steamid64=synthetic.steamid64,
        map_id=990000,
        mode_id=200,
        stage=0,
        time_seconds=Decimal("35.289"),
        created_on=synthetic.recorded_at,
    )
    replay_dir = tmp_path / "replays"
    replay_dir.mkdir()
    (replay_dir / "sample.replay").write_bytes(synthetic.replay_bytes)

    result = await import_run_replays_from_paths([replay_dir], dry_run=True)

    assert result.scanned == 1
    assert result.matched == 1
    assert result.imported == 0
    assert not get_run_replay_path(
        map_name="kz_dry_run",
        replay_id=record.uuid,
    ).exists()


async def test_import_run_replays_supports_zip_and_7z_archives(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _bind_import_session(monkeypatch, db)
    monkeypatch.setattr(settings, "REPLAY_STORAGE_DIR", tmp_path / "storage")

    zip_replay = build_synthetic_run_replay(
        map_name="kz_zip_map",
        steam_account_id=12345,
    )
    await _seed_dependencies(db, steamid64=zip_replay.steamid64, map_name="kz_zip_map")
    zip_record = await _create_record(
        db,
        id=992010,
        steamid64=zip_replay.steamid64,
        map_id=990000,
        mode_id=200,
        stage=0,
        time_seconds=Decimal("35.289"),
        created_on=zip_replay.recorded_at,
    )

    archive_zip = tmp_path / "runs.zip"
    with zipfile.ZipFile(archive_zip, mode="w") as archive:
        archive.writestr("nested/zip.replay", zip_replay.replay_bytes)

    seven_replay = build_synthetic_run_replay(
        map_name="kz_7z_map",
        steam_account_id=12346,
    )
    await _create_player(db, steamid64=seven_replay.steamid64, name="Import Runner 7z")
    await _create_map(db, id=990001, name="kz_7z_map")
    seven_record = await _create_record(
        db,
        id=992011,
        steamid64=seven_replay.steamid64,
        map_id=990001,
        mode_id=200,
        stage=0,
        time_seconds=Decimal("35.289"),
        created_on=seven_replay.recorded_at,
    )
    source_dir = tmp_path / "seven-src"
    source_dir.mkdir()
    source_file = source_dir / "seven.replay"
    source_file.write_bytes(seven_replay.replay_bytes)
    archive_7z = tmp_path / "runs.7z"
    with py7zr.SevenZipFile(archive_7z, mode="w") as archive:
        archive.write(source_file, arcname="nested/seven.replay")

    zip_result = await import_run_replays_from_paths([archive_zip])
    seven_result = await import_run_replays_from_paths([archive_7z])

    assert zip_result.imported == 1
    assert seven_result.imported == 1
    assert get_run_replay_path(
        map_name="kz_zip_map",
        replay_id=zip_record.uuid,
    ).exists()
    assert get_run_replay_path(
        map_name="kz_7z_map",
        replay_id=seven_record.uuid,
    ).exists()


async def test_import_run_replays_skips_existing_replay_file(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _bind_import_session(monkeypatch, db)
    monkeypatch.setattr(settings, "REPLAY_STORAGE_DIR", tmp_path)
    synthetic = build_synthetic_run_replay(map_name="kz_existing_map")
    await _seed_dependencies(
        db,
        steamid64=synthetic.steamid64,
        map_name="kz_existing_map",
    )
    record = await _create_record(
        db,
        id=992020,
        steamid64=synthetic.steamid64,
        map_id=990000,
        mode_id=200,
        stage=0,
        time_seconds=Decimal("35.289"),
        created_on=synthetic.recorded_at,
    )
    existing_path = get_run_replay_path(
        map_name="kz_existing_map",
        replay_id=record.uuid,
    )
    existing_path.parent.mkdir(parents=True, exist_ok=True)
    existing_path.write_bytes(b"existing")
    replay_path = tmp_path / "existing.replay"
    replay_path.write_bytes(synthetic.replay_bytes)

    result = await import_run_replays_from_paths([replay_path])

    assert result.matched == 1
    assert result.already_available == 1
    assert result.imported == 0
    assert existing_path.read_bytes() == b"existing"


async def test_import_run_replays_counts_ambiguous_and_invalid_style_failures(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _bind_import_session(monkeypatch, db)
    monkeypatch.setattr(settings, "REPLAY_STORAGE_DIR", tmp_path)

    ambiguous = build_synthetic_run_replay(map_name="kz_ambiguous_import")
    await _seed_dependencies(
        db,
        steamid64=ambiguous.steamid64,
        map_name="kz_ambiguous_import",
    )
    for record_id, created_on in (
        (992030, ambiguous.recorded_at - timedelta(hours=1)),
        (992031, ambiguous.recorded_at + timedelta(hours=1)),
    ):
        await _create_record(
            db,
            id=record_id,
            steamid64=ambiguous.steamid64,
            map_id=990000,
            mode_id=200,
            stage=0,
            time_seconds=Decimal("35.289"),
            created_on=created_on,
        )

    invalid_style = build_synthetic_run_replay(
        map_name="kz_invalid_style",
        steam_account_id=22345,
        style_index=1,
    )
    replay_dir = tmp_path / "mixed"
    replay_dir.mkdir()
    (replay_dir / "ambiguous.replay").write_bytes(ambiguous.replay_bytes)
    (replay_dir / "invalid-style.replay").write_bytes(invalid_style.replay_bytes)

    result = await import_run_replays_from_paths([replay_dir])

    assert result.scanned == 2
    assert result.ambiguous == 1
    assert result.failed == 2
    assert result.imported == 0
