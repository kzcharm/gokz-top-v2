"""Exercise real archive handling and simulated SteamCMD download output."""

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock
from zipfile import ZipFile

import py7zr
import pytest

from app.models import Map, MapFileDistribution
from app.services import map_file_distribution as distribution


def configure_storage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        distribution.settings, "MAP_FILE_STORAGE_DIR", tmp_path / "storage"
    )
    distribution._ensure_storage_dirs()


@pytest.mark.asyncio
async def test_real_seed_archive_extracts_bsps_and_copies_package(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    configure_storage(monkeypatch, tmp_path)
    source = tmp_path / "kz_seed_contract.bsp"
    source.write_bytes(b"VBSP test map")
    package = tmp_path / "maps.7z"
    with py7zr.SevenZipFile(package, "w") as archive:
        archive.write(source, arcname="nested/kz_seed_contract.bsp")
    result = await distribution.seed_map_package(
        package_path=package, copy_package=True
    )
    assert result.processed == result.extracted == 1
    assert result.package_copied
    assert (
        distribution._raw_bsp_path("kz_seed_contract").read_bytes()
        == source.read_bytes()
    )
    assert distribution._full_package_path().read_bytes() == package.read_bytes()
    assert not list(distribution._tmp_dir().glob("seed-*"))
    assert not (
        await distribution.seed_map_package(package_path=package)
    ).package_copied
    with pytest.raises(distribution.MapFileDistributionError, match="does not exist"):
        await distribution.seed_map_package(package_path=tmp_path / "missing.7z")
    assert (
        distribution._release_date(datetime(2025, 1, 1))
        == datetime(2025, 1, 1, tzinfo=UTC).date()
    )
    assert (
        distribution._release_date(
            datetime(2025, 1, 1, tzinfo=timezone(timedelta(hours=2)))
        )
        == datetime(2024, 12, 31, tzinfo=UTC).date()
    )


@pytest.mark.asyncio
async def test_workshop_download_validates_output_and_copies_a_unique_map(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    configure_storage(monkeypatch, tmp_path)
    command = AsyncMock()
    monkeypatch.setattr(distribution, "_run_command_async", command)
    map_obj = Map(id=1, name="kz_download_contract", workshop_id=123)
    with pytest.raises(
        distribution.MapFileDistributionError, match="content directory"
    ):
        await distribution._download_workshop_bsp(map_obj=map_obj)
    content = (
        distribution._workshop_dir()
        / "steamapps/workshop/content"
        / str(distribution.settings.MAP_DISTRIBUTION_STEAM_APP_ID)
        / "123"
    )
    content.mkdir(parents=True)
    with ZipFile(content / "data.bin", "w") as archive:
        archive.writestr("maps/", "")
        archive.writestr("maps/kz_download_contract.bsp", b"downloaded BSP")
    prepared = await distribution._prepare_map_bsp(
        map_obj=map_obj,
        distribution=MapFileDistribution(
            map_id=1,
            map_name=map_obj.name,
            bsp_download_url="https://storage.example/old.bsp",
        ),
    )
    assert prepared.source == "workshop"
    assert prepared.raw_path.read_bytes() == b"downloaded BSP"
    assert str(map_obj.workshop_id) in command.await_args.args[0]
    seeded = await distribution._prepare_map_bsp(
        map_obj=Map(id=2, name=map_obj.name), distribution=None
    )
    assert seeded.source == "seed"
    existing = MapFileDistribution(
        map_id=2,
        map_name=map_obj.name,
        bsp_download_url="https://storage.example/old.bsp",
    )
    assert (
        await distribution._prepare_map_bsp(
            map_obj=Map(id=2, name=map_obj.name), distribution=existing
        )
    ).source == "seed"
    with pytest.raises(distribution.MapFileDistributionError, match="no workshop id"):
        await distribution._prepare_map_bsp(
            map_obj=Map(id=3, name="kz_missing"), distribution=None
        )


def test_distribution_current_requires_matching_name_hash_and_update_time(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    configure_storage(monkeypatch, tmp_path)
    now = datetime(2025, 1, 1, tzinfo=UTC)
    map_obj = Map(id=1, name="kz_current_contract", updated_at=now)
    distribution._raw_bsp_path(map_obj.name).write_bytes(b"BSP")
    row = MapFileDistribution(map_id=1, map_name=map_obj.name)
    assert not distribution._is_distribution_current(map_obj=map_obj, distribution=row)
    row.bsp_download_url, row.bsp_sha256 = "https://storage.example/map.bsp", "hash"
    row.map_name = "kz_old_name"
    assert not distribution._is_distribution_current(map_obj=map_obj, distribution=row)
    row.map_name = map_obj.name
    assert not distribution._is_distribution_current(map_obj=map_obj, distribution=row)
    row.map_updated_at = now
    assert distribution._is_distribution_current(map_obj=map_obj, distribution=row)
    content = tmp_path / "ambiguous"
    content.mkdir()
    (content / "one.bsp").write_bytes(b"one")
    (content / "two.bsp").write_bytes(b"two")
    with pytest.raises(distribution.MapFileDistributionError, match="unique BSP"):
        distribution._find_workshop_bsp(content_dir=content, map_name="missing")
    monkeypatch.setattr(distribution.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(distribution.r2_storage, "is_configured", lambda: False)
    with pytest.raises(distribution.MapFileDistributionError, match="not configured"):
        distribution._require_enabled()
