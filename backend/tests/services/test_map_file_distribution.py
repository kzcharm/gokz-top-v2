from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile

import pytest
from sqlmodel import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import Map, MapFileDistribution
from app.services import map_file_distribution as distribution


def _set_production_distribution_settings(
    monkeypatch: pytest.MonkeyPatch,
    *,
    storage_dir: Path,
) -> None:
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "MAP_FILE_STORAGE_DIR", storage_dir)
    monkeypatch.setattr(settings, "R2_ACCOUNT_ID", "account")
    monkeypatch.setattr(settings, "R2_ACCESS_KEY_ID", "access-key")
    monkeypatch.setattr(settings, "R2_SECRET_ACCESS_KEY", "secret-key")
    monkeypatch.setattr(settings, "R2_BUCKET_NAME", "bucket")
    monkeypatch.setattr(settings, "R2_PUBLIC_BASE_URL", "https://cdn.example.com")


@pytest.mark.asyncio
async def test_sync_map_files_is_disabled_outside_production(
    db: AsyncSession,
) -> None:
    result = await distribution.sync_map_files(session=db)

    assert result.disabled is True
    assert result.processed == 0


@pytest.mark.asyncio
async def test_sync_map_files_uploads_seeded_raw_bsp(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _set_production_distribution_settings(monkeypatch, storage_dir=tmp_path)
    map_id = 991001
    map_name = "kz_distribution_seeded"
    other_map_id = 991002
    other_map_name = "kz_distribution_existing_raw"
    await db.exec(delete(MapFileDistribution).where(MapFileDistribution.map_id == map_id))
    await db.exec(
        delete(MapFileDistribution).where(MapFileDistribution.map_id == other_map_id)
    )
    await db.exec(delete(Map).where(Map.id == map_id))
    await db.exec(delete(Map).where(Map.id == other_map_id))
    db.add(
        Map(
            id=map_id,
            name=map_name,
            filesize=4,
            validated=True,
            difficulty=1,
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
            updated_at=datetime(2026, 6, 5, tzinfo=UTC),
            approved_by_steamid64=0,
            workshop_id=None,
        )
    )
    db.add(
        Map(
            id=other_map_id,
            name=other_map_name,
            filesize=4,
            validated=True,
            difficulty=1,
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
            updated_at=datetime(2026, 6, 5, tzinfo=UTC),
            approved_by_steamid64=0,
            workshop_id=None,
        )
    )
    await db.commit()
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True)
    (raw_dir / f"{map_name}.bsp").write_bytes(b"bsp-bytes")
    (raw_dir / f"{other_map_name}.bsp").write_bytes(b"other-bsp-bytes")
    uploaded_keys: list[str] = []

    async def _fake_put_file(
        *,
        key: str,
        path: Path,
        content_type: str,
        cache_control: str | None = None,
    ) -> str:
        assert path.exists()
        assert content_type
        assert cache_control
        uploaded_keys.append(key)
        return f"https://cdn.example.com/{key}"

    monkeypatch.setattr(distribution.r2_storage, "put_file", _fake_put_file)

    async def _fake_sync_full_package(
        *,
        raw_paths_by_name: dict[str, Path],
        changed_names: set[str],
    ) -> bool:
        assert raw_paths_by_name == {
            map_name: raw_dir / f"{map_name}.bsp",
            other_map_name: raw_dir / f"{other_map_name}.bsp",
        }
        assert changed_names == {map_name}
        return False

    monkeypatch.setattr(distribution, "_sync_full_package", _fake_sync_full_package)

    async def _fake_upload_release_packages(
        *,
        session: AsyncSession,
        processed_maps: object,
    ) -> int:
        assert session is db
        assert processed_maps
        return 0

    monkeypatch.setattr(
        distribution, "_upload_release_packages", _fake_upload_release_packages
    )

    result = await distribution.sync_map_files(session=db, map_ids=[map_id])

    assert result.processed == 1
    assert result.uploaded == 1
    assert result.bz2_uploaded == 1
    assert result.errors == 0
    assert uploaded_keys == [
        f"maps/{map_name}.bsp",
        f"maps/{map_name}.bsp.bz2",
    ]
    row = await db.get(MapFileDistribution, map_id)
    assert row is not None
    assert row.bsp_download_url == f"https://cdn.example.com/maps/{map_name}.bsp"
    assert row.bz2_download_url == f"https://cdn.example.com/maps/{map_name}.bsp.bz2"
    assert row.source == "seed"
    assert row.last_error is None


def test_find_workshop_bsp_accepts_nested_exact_bsp(tmp_path: Path) -> None:
    content_dir = tmp_path / "content"
    nested_dir = content_dir / "mymaps"
    nested_dir.mkdir(parents=True)
    bsp_path = nested_dir / "kz_nested.bsp"
    bsp_path.write_bytes(b"bsp-bytes")

    assert (
        distribution._find_workshop_bsp(
            content_dir=content_dir,
            map_name="kz_nested",
        )
        == bsp_path
    )


def test_find_workshop_bsp_extracts_steamcmd_legacy_zip_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _set_production_distribution_settings(monkeypatch, storage_dir=tmp_path)
    content_dir = tmp_path / "workshop" / "steamapps" / "workshop" / "content" / "730"
    content_dir.mkdir(parents=True)
    archive_path = content_dir / "14398412976525154847_legacy.bin"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("mymaps/kz_bloodlust.bsp", b"bsp-bytes")

    extracted_path = distribution._find_workshop_bsp(
        content_dir=content_dir,
        map_name="kz_bloodlust",
    )

    assert extracted_path.name == "kz_bloodlust.bsp"
    assert extracted_path.read_bytes() == b"bsp-bytes"
    assert extracted_path.parent.parent == tmp_path / "tmp"


@pytest.mark.asyncio
async def test_sync_full_package_uses_incremental_update_and_delete(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _set_production_distribution_settings(monkeypatch, storage_dir=tmp_path)
    raw_dir = tmp_path / "raw"
    package_dir = tmp_path / "packages"
    raw_dir.mkdir(parents=True)
    package_dir.mkdir(parents=True)
    raw_path = raw_dir / "kz_current.bsp"
    raw_path.write_bytes(b"bsp")
    (package_dir / "GlobalMaps.7z").write_bytes(b"archive")

    async def _fake_list_archive_bsp_entries(_archive_path: Path) -> set[str]:
        return {"kz_current.bsp", "kz_stale.bsp"}

    commands: list[list[str]] = []

    async def _fake_run_command_async(
        args: list[str],
        *,
        cwd: Path | None = None,
    ) -> object:
        assert cwd in {None, raw_dir}
        commands.append(args)
        return object()

    monkeypatch.setattr(
        distribution, "_list_archive_bsp_entries", _fake_list_archive_bsp_entries
    )
    monkeypatch.setattr(distribution, "_run_command_async", _fake_run_command_async)
    entry_commands: list[tuple[str, Path, list[str]]] = []

    async def _fake_run_7z_entry_command(
        *,
        command: str,
        archive_path: Path,
        entries: list[str],
    ) -> None:
        entry_commands.append((command, archive_path, entries))

    monkeypatch.setattr(distribution, "_run_7z_entry_command", _fake_run_7z_entry_command)

    changed = await distribution._sync_full_package(
        raw_paths_by_name={"kz_current": raw_path},
        changed_names={"kz_current"},
    )

    assert changed is True
    assert entry_commands == [
        ("d", package_dir / "GlobalMaps.7z", ["kz_stale.bsp"]),
        ("u", package_dir / "GlobalMaps.7z", ["kz_current.bsp"]),
    ]
    assert commands == [
        [settings.SEVENZIP_PATH, "t", str(package_dir / "GlobalMaps.7z")],
    ]
