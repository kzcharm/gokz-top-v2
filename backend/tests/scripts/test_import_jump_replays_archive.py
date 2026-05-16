from __future__ import annotations

import zipfile
from contextlib import asynccontextmanager

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.import_jump_replays_archive import import_jump_replays_archive_from_path
from app.models import Jumpstat, ServerGroupUpdate
from app.services.jump_replay_storage import get_jump_replay_path
from tests.utils.jump_replay import build_synthetic_jump_replay
from tests.utils.server import create_server_group as create_test_server_group

pytestmark = pytest.mark.asyncio


def _bind_import_session(
    monkeypatch: pytest.MonkeyPatch,
    db: AsyncSession,
) -> None:
    @asynccontextmanager
    async def _session_maker():
        yield db

    monkeypatch.setattr(
        "app.import_jump_replays_archive.async_session_maker",
        _session_maker,
    )


async def test_import_jump_replays_archive_creates_rows_and_replay_files(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _bind_import_session(monkeypatch, db)
    monkeypatch.setattr(settings, "JUMP_REPLAY_STORAGE_DIR", tmp_path)
    group, _api_key = await create_test_server_group(db, name="AXE GOKZ")
    synthetic = build_synthetic_jump_replay()
    archive_path = tmp_path / "jumps.zip"
    with zipfile.ZipFile(archive_path, mode="w") as archive:
        archive.writestr("_jumps/legacy/0_KZT_NRM.replay", synthetic.replay_bytes)

    result = await import_jump_replays_archive_from_path(
        archive_path,
        server_group=group.name,
    )

    assert result.scanned == 1
    assert result.inserted == 1
    assert result.deduped == 0
    assert result.failed == 0

    jumpstat = (await db.exec(select(Jumpstat))).one()
    assert jumpstat.server_group_id == group.id
    assert (
        get_jump_replay_path(jumpstat_id=jumpstat.id).read_bytes()
        == synthetic.replay_bytes
    )


async def test_import_jump_replays_archive_deduplicates_matching_signature(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _bind_import_session(monkeypatch, db)
    monkeypatch.setattr(settings, "JUMP_REPLAY_STORAGE_DIR", tmp_path)
    group, _api_key = await create_test_server_group(db, name="AXE Import Group")
    synthetic = build_synthetic_jump_replay()
    archive_path = tmp_path / "jumps.zip"
    with zipfile.ZipFile(archive_path, mode="w") as archive:
        archive.writestr("_jumps/first.replay", synthetic.replay_bytes)
        archive.writestr("_jumps/second.replay", synthetic.replay_bytes)

    result = await import_jump_replays_archive_from_path(
        archive_path,
        server_group=group.name,
    )

    assert result.scanned == 2
    assert result.inserted == 1
    assert result.deduped == 1
    assert result.failed == 0
    jumpstats = list((await db.exec(select(Jumpstat))).all())
    assert len(jumpstats) == 1


async def test_import_jump_replays_archive_dry_run_skips_writes(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _bind_import_session(monkeypatch, db)
    monkeypatch.setattr(settings, "JUMP_REPLAY_STORAGE_DIR", tmp_path)
    group, _api_key = await create_test_server_group(db, name="AXE Dry Run Group")
    synthetic = build_synthetic_jump_replay()
    archive_path = tmp_path / "jumps.zip"
    with zipfile.ZipFile(archive_path, mode="w") as archive:
        archive.writestr("_jumps/sample.replay", synthetic.replay_bytes)

    result = await import_jump_replays_archive_from_path(
        archive_path,
        server_group=group.name,
        dry_run=True,
    )

    assert result.scanned == 1
    assert result.inserted == 0
    assert result.deduped == 0
    assert result.failed == 0
    assert list((await db.exec(select(Jumpstat))).all()) == []


async def test_import_jump_replays_archive_rejects_ambiguous_group_identifier(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _bind_import_session(monkeypatch, db)
    first_group, _api_key = await create_test_server_group(db, name="First Group")
    await crud.update_server_group(
        session=db,
        group=first_group,
        group_in=ServerGroupUpdate(custom_id="axe"),
    )
    await create_test_server_group(db, name="axe")
    synthetic = build_synthetic_jump_replay()
    archive_path = tmp_path / "jumps.zip"
    with zipfile.ZipFile(archive_path, mode="w") as archive:
        archive.writestr("_jumps/sample.replay", synthetic.replay_bytes)

    with pytest.raises(ValueError, match="ambiguous"):
        await import_jump_replays_archive_from_path(
            archive_path,
            server_group="axe",
        )


async def test_import_jump_replays_archive_rejects_missing_group_identifier(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _bind_import_session(monkeypatch, db)
    synthetic = build_synthetic_jump_replay()
    archive_path = tmp_path / "jumps.zip"
    with zipfile.ZipFile(archive_path, mode="w") as archive:
        archive.writestr("_jumps/sample.replay", synthetic.replay_bytes)

    with pytest.raises(ValueError, match="was not found"):
        await import_jump_replays_archive_from_path(
            archive_path,
            server_group="missing-group",
        )
