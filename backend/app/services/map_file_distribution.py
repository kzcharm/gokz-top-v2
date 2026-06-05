from __future__ import annotations

import asyncio
import bz2
import logging
import shutil
import subprocess
import uuid
import zipfile
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import py7zr
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import (
    Map,
    MapFileDistribution,
    MapFileDistributionSyncResult,
    MapFileSeedResult,
    MapPackageRelease,
    get_datetime_utc,
)
from app.services import r2_storage

logger = logging.getLogger(__name__)

FULL_PACKAGE_KEY = "packages/GlobalMaps.7z"
FULL_PACKAGE_NAME = "GlobalMaps.7z"
MAP_BSP_CONTENT_TYPE = "application/octet-stream"
MAP_BZ2_CONTENT_TYPE = "application/x-bzip2"
SEVENZIP_CONTENT_TYPE = "application/x-7z-compressed"
ZIP_CONTENT_TYPE = "application/zip"
MAP_CACHE_CONTROL = "public, max-age=3600"
PACKAGE_CACHE_CONTROL = "public, max-age=3600"


class MapFileDistributionError(RuntimeError):
    pass


class MapFileDistributionDisabledError(MapFileDistributionError):
    pass


@dataclass(frozen=True, slots=True)
class _PreparedMap:
    map_obj: Map
    raw_path: Path
    source: str


@dataclass(frozen=True, slots=True)
class _ProcessedMap:
    map_obj: Map
    raw_path: Path


def _storage_root() -> Path:
    return settings.MAP_FILE_STORAGE_DIR


def _raw_dir() -> Path:
    return _storage_root() / "raw"


def _workshop_dir() -> Path:
    return _storage_root() / "workshop"


def _package_dir() -> Path:
    return _storage_root() / "packages"


def _tmp_dir() -> Path:
    return _storage_root() / "tmp"


def _full_package_path() -> Path:
    return _package_dir() / FULL_PACKAGE_NAME


def _bsp_filename(map_name: str) -> str:
    return f"{map_name}.bsp"


def _raw_bsp_path(map_name: str) -> Path:
    return _raw_dir() / _bsp_filename(map_name)


def _release_date(value: datetime) -> date:
    if value.tzinfo is not None:
        return value.astimezone(UTC).date()
    return value.replace(tzinfo=UTC).date()


def _ensure_storage_dirs() -> None:
    for path in (_raw_dir(), _workshop_dir(), _package_dir(), _tmp_dir()):
        path.mkdir(parents=True, exist_ok=True)


def _require_enabled() -> None:
    if settings.ENVIRONMENT != "production":
        raise MapFileDistributionDisabledError(
            "Map file distribution is enabled only in production"
        )
    if not r2_storage.is_configured():
        raise MapFileDistributionError("Cloudflare R2 storage is not configured")


def _run_command(args: Sequence[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    logger.debug("Running map distribution command: %s", " ".join(args))
    return subprocess.run(
        list(args),
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
    )


async def _run_command_async(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return await asyncio.to_thread(_run_command, args, cwd=cwd)


async def seed_map_package(
    *,
    package_path: Path,
    copy_package: bool = False,
) -> MapFileSeedResult:
    if not package_path.exists():
        raise MapFileDistributionError(f"Map package does not exist: {package_path}")

    _ensure_storage_dirs()
    extraction_dir = _tmp_dir() / f"seed-{uuid.uuid4()}"
    extraction_dir.mkdir(parents=True, exist_ok=False)
    try:
        await asyncio.to_thread(_extract_7z, package_path, extraction_dir)
        bsp_paths = sorted(extraction_dir.rglob("*.bsp"))
        for bsp_path in bsp_paths:
            destination = _raw_bsp_path(bsp_path.stem)
            await asyncio.to_thread(_atomic_copy, bsp_path, destination)

        package_copied = False
        if copy_package:
            await asyncio.to_thread(_atomic_copy, package_path, _full_package_path())
            package_copied = True

        return MapFileSeedResult(
            processed=len(bsp_paths),
            extracted=len(bsp_paths),
            package_copied=package_copied,
        )
    finally:
        await asyncio.to_thread(shutil.rmtree, extraction_dir, True)


def _extract_7z(package_path: Path, destination: Path) -> None:
    with py7zr.SevenZipFile(package_path, mode="r") as archive:
        archive.extractall(path=destination)


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4()}.tmp")
    shutil.copy2(source, temporary)
    temporary.replace(destination)


async def sync_map_files(
    *,
    session: AsyncSession,
    force: bool = False,
    map_ids: Sequence[int] | None = None,
) -> MapFileDistributionSyncResult:
    try:
        _require_enabled()
    except MapFileDistributionDisabledError:
        return MapFileDistributionSyncResult(disabled=True)

    _ensure_storage_dirs()
    maps = await _load_target_maps(session=session, map_ids=map_ids)
    distributions = await _load_distributions(session=session, map_ids=[map_obj.id for map_obj in maps])
    distribution_by_map_id = {row.map_id: row for row in distributions}
    result = MapFileDistributionSyncResult()
    processed_maps: list[_ProcessedMap] = []

    for map_obj in maps:
        result.processed += 1
        distribution = distribution_by_map_id.get(map_obj.id)
        if not force and _is_distribution_current(map_obj=map_obj, distribution=distribution):
            result.skipped += 1
            continue

        try:
            prepared = await _prepare_map_bsp(map_obj=map_obj, distribution=distribution)
            if prepared.source == "workshop":
                result.downloaded += 1

            upload_result = await _upload_map_files(
                session=session,
                prepared=prepared,
                distribution=distribution,
            )
            distribution_by_map_id[map_obj.id] = upload_result
            result.uploaded += 1
            if upload_result.bz2_download_url is not None:
                result.bz2_uploaded += 1
            processed_maps.append(_ProcessedMap(map_obj=map_obj, raw_path=prepared.raw_path))
        except Exception as exc:
            logger.warning("Failed to distribute map file for %s: %s", map_obj.name, exc)
            await _record_map_error(
                session=session,
                map_obj=map_obj,
                distribution=distribution,
                error=str(exc),
            )
            result.errors += 1

    all_validated_maps = await _load_target_maps(session=session, map_ids=None)
    raw_paths_by_name = {
        map_obj.name: _raw_bsp_path(map_obj.name)
        for map_obj in all_validated_maps
        if _raw_bsp_path(map_obj.name).exists()
    }
    package_changed = await _sync_full_package(
        raw_paths_by_name=raw_paths_by_name,
        changed_names={processed.map_obj.name for processed in processed_maps},
    )
    if package_changed:
        await r2_storage.put_file(
            key=FULL_PACKAGE_KEY,
            path=_full_package_path(),
            content_type=SEVENZIP_CONTENT_TYPE,
            cache_control=PACKAGE_CACHE_CONTROL,
        )
        result.package_uploaded = 1

    release_uploads = await _upload_release_packages(
        session=session,
        processed_maps=processed_maps,
    )
    result.release_packages_uploaded = release_uploads
    return result


async def _load_target_maps(
    *,
    session: AsyncSession,
    map_ids: Sequence[int] | None,
) -> list[Map]:
    statement = select(Map).where(col(Map.id) > 0, col(Map.validated).is_(True))
    if map_ids:
        statement = statement.where(col(Map.id).in_(list(map_ids)))
    rows = await session.exec(statement.order_by(col(Map.name).asc()))
    return list(rows.all())


async def _load_distributions(
    *,
    session: AsyncSession,
    map_ids: Sequence[int],
) -> list[MapFileDistribution]:
    if not map_ids:
        return []
    rows = await session.exec(
        select(MapFileDistribution).where(col(MapFileDistribution.map_id).in_(list(map_ids)))
    )
    return list(rows.all())


def _is_distribution_current(
    *,
    map_obj: Map,
    distribution: MapFileDistribution | None,
) -> bool:
    raw_path = _raw_bsp_path(map_obj.name)
    if distribution is None or not raw_path.exists():
        return False
    if not distribution.bsp_download_url or not distribution.bsp_sha256:
        return False
    if distribution.map_name != map_obj.name:
        return False
    if distribution.map_updated_at is None:
        return False
    return distribution.map_updated_at >= map_obj.updated_at


async def _prepare_map_bsp(
    *,
    map_obj: Map,
    distribution: MapFileDistribution | None,
) -> _PreparedMap:
    raw_path = _raw_bsp_path(map_obj.name)
    if raw_path.exists() and (
        distribution is None or not distribution.bsp_download_url
    ):
        return _PreparedMap(map_obj=map_obj, raw_path=raw_path, source="seed")

    if map_obj.workshop_id is None:
        if raw_path.exists():
            return _PreparedMap(map_obj=map_obj, raw_path=raw_path, source="seed")
        raise MapFileDistributionError("Map has no workshop id and no seeded BSP")

    downloaded_bsp = await _download_workshop_bsp(map_obj=map_obj)
    await asyncio.to_thread(_atomic_copy, downloaded_bsp, raw_path)
    return _PreparedMap(map_obj=map_obj, raw_path=raw_path, source="workshop")


async def _download_workshop_bsp(*, map_obj: Map) -> Path:
    assert map_obj.workshop_id is not None
    await _run_command_async(
        [
            settings.STEAMCMD_PATH,
            "+force_install_dir",
            str(_workshop_dir()),
            "+login",
            "anonymous",
            "+workshop_download_item",
            str(settings.MAP_DISTRIBUTION_STEAM_APP_ID),
            str(map_obj.workshop_id),
            "validate",
            "+quit",
        ]
    )
    content_dir = (
        _workshop_dir()
        / "steamapps"
        / "workshop"
        / "content"
        / str(settings.MAP_DISTRIBUTION_STEAM_APP_ID)
        / str(map_obj.workshop_id)
    )
    if not content_dir.exists():
        raise MapFileDistributionError(
            f"Steam Workshop item {map_obj.workshop_id} did not produce a content directory"
        )
    return _find_workshop_bsp(content_dir=content_dir, map_name=map_obj.name)


def _find_workshop_bsp(*, content_dir: Path, map_name: str) -> Path:
    bsp_filename = _bsp_filename(map_name)
    exact_matches = sorted(
        path
        for path in content_dir.rglob("*")
        if path.is_file() and path.name.casefold() == bsp_filename.casefold()
    )
    if len(exact_matches) == 1:
        return exact_matches[0]

    bsp_paths = sorted(
        path
        for path in content_dir.rglob("*")
        if path.is_file() and path.suffix.casefold() == ".bsp"
    )
    if len(bsp_paths) == 1:
        return bsp_paths[0]

    archived_bsp = _extract_workshop_archive_bsp(
        content_dir=content_dir,
        map_name=map_name,
    )
    if archived_bsp is not None:
        return archived_bsp

    raise MapFileDistributionError(
        f"Steam Workshop content did not contain a unique BSP for {map_name}"
    )


def _extract_workshop_archive_bsp(*, content_dir: Path, map_name: str) -> Path | None:
    bsp_filename = _bsp_filename(map_name)
    exact_candidates: list[tuple[Path, zipfile.ZipInfo]] = []
    bsp_candidates: list[tuple[Path, zipfile.ZipInfo]] = []

    for archive_path in sorted(path for path in content_dir.rglob("*") if path.is_file()):
        if archive_path.suffix.casefold() not in {".bin", ".zip"}:
            continue
        if not zipfile.is_zipfile(archive_path):
            continue
        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                filename = Path(info.filename).name
                if filename.casefold() == bsp_filename.casefold():
                    exact_candidates.append((archive_path, info))
                if filename.casefold().endswith(".bsp"):
                    bsp_candidates.append((archive_path, info))

    candidates = exact_candidates or bsp_candidates
    if len(candidates) != 1:
        return None

    archive_path, info = candidates[0]
    output_dir = _tmp_dir() / f"workshop-{uuid.uuid4()}"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / Path(info.filename).name
    with zipfile.ZipFile(archive_path) as archive:
        with archive.open(info) as source, output_path.open("wb") as target:
            shutil.copyfileobj(source, target)
    return output_path


async def _upload_map_files(
    *,
    session: AsyncSession,
    prepared: _PreparedMap,
    distribution: MapFileDistribution | None,
) -> MapFileDistribution:
    map_obj = prepared.map_obj
    raw_path = prepared.raw_path
    now = get_datetime_utc()
    bsp_key = f"maps/{_bsp_filename(map_obj.name)}"
    bsp_url = await r2_storage.put_file(
        key=bsp_key,
        path=raw_path,
        content_type=MAP_BSP_CONTENT_TYPE,
        cache_control=MAP_CACHE_CONTROL,
    )
    file_size = raw_path.stat().st_size
    file_hash = await asyncio.to_thread(r2_storage.hash_file_sha256, raw_path)
    row = distribution or MapFileDistribution(map_id=map_obj.id, map_name=map_obj.name)
    old_bz2_key = row.bz2_r2_key
    row.map_name = map_obj.name
    row.workshop_id = map_obj.workshop_id
    row.map_updated_at = map_obj.updated_at
    row.bsp_size = file_size
    row.bsp_sha256 = file_hash
    row.bsp_r2_key = bsp_key
    row.bsp_download_url = bsp_url
    row.source = prepared.source
    row.synced_at = now
    row.uploaded_at = now
    row.last_error = None

    if file_size < settings.MAP_DISTRIBUTION_BZ2_MAX_BYTES:
        bz2_path = await asyncio.to_thread(_compress_bz2, raw_path)
        try:
            bz2_key = f"maps/{_bsp_filename(map_obj.name)}.bz2"
            row.bz2_download_url = await r2_storage.put_file(
                key=bz2_key,
                path=bz2_path,
                content_type=MAP_BZ2_CONTENT_TYPE,
                cache_control=MAP_CACHE_CONTROL,
            )
            row.bz2_r2_key = bz2_key
            row.bz2_size = bz2_path.stat().st_size
        finally:
            bz2_path.unlink(missing_ok=True)
    else:
        if old_bz2_key:
            await r2_storage.delete_object(key=old_bz2_key)
        row.bz2_r2_key = None
        row.bz2_download_url = None
        row.bz2_size = None

    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


def _compress_bz2(path: Path) -> Path:
    destination = _tmp_dir() / f"{path.name}.{uuid.uuid4()}.bz2"
    with path.open("rb") as source, bz2.open(destination, "wb") as target:
        shutil.copyfileobj(source, target, length=1024 * 1024)
    return destination


async def _record_map_error(
    *,
    session: AsyncSession,
    map_obj: Map,
    distribution: MapFileDistribution | None,
    error: str,
) -> None:
    row = distribution or MapFileDistribution(map_id=map_obj.id, map_name=map_obj.name)
    row.map_name = map_obj.name
    row.workshop_id = map_obj.workshop_id
    row.map_updated_at = map_obj.updated_at
    row.synced_at = get_datetime_utc()
    row.last_error = error[:4000]
    session.add(row)
    await session.commit()


async def _sync_full_package(
    *,
    raw_paths_by_name: dict[str, Path],
    changed_names: set[str],
) -> bool:
    archive_path = _full_package_path()
    valid_entries = {_bsp_filename(name) for name in raw_paths_by_name}
    if not raw_paths_by_name:
        return False
    if not archive_path.exists():
        await _rebuild_full_package(raw_paths=raw_paths_by_name.values())
        return True

    try:
        existing_entries = await _list_archive_bsp_entries(archive_path)
        stale_entries = sorted(existing_entries - valid_entries)
        changed_entries = sorted(
            _bsp_filename(name)
            for name in changed_names
            if name in raw_paths_by_name
        )
        if not stale_entries and not changed_entries:
            return False
        if stale_entries:
            await _run_7z_entry_command(
                command="d",
                archive_path=archive_path,
                entries=stale_entries,
            )
        if changed_entries:
            await _run_7z_entry_command(
                command="u",
                archive_path=archive_path,
                entries=changed_entries,
            )
        await _run_command_async([settings.SEVENZIP_PATH, "t", str(archive_path.resolve())])
        return True
    except Exception:
        logger.exception("Incremental GlobalMaps.7z update failed; rebuilding archive")
        await _rebuild_full_package(raw_paths=raw_paths_by_name.values())
        return True


async def _list_archive_bsp_entries(archive_path: Path) -> set[str]:
    completed = await _run_command_async(
        [settings.SEVENZIP_PATH, "l", "-slt", str(archive_path.resolve())]
    )
    entries: set[str] = set()
    for line in completed.stdout.splitlines():
        if not line.startswith("Path = "):
            continue
        value = line.removeprefix("Path = ").strip()
        if value.endswith(".bsp") and "/" not in value and "\\" not in value:
            entries.add(value)
    return entries


async def _rebuild_full_package(*, raw_paths: Iterable[Path]) -> None:
    archive_path = _full_package_path()
    raw_names = sorted(path.name for path in raw_paths)
    if not raw_names:
        return
    temporary_archive = archive_path.with_name(f".{archive_path.name}.{uuid.uuid4()}.tmp")
    list_file = _tmp_dir() / f"7z-list-{uuid.uuid4()}.txt"
    list_file.write_text("\n".join(raw_names) + "\n")
    try:
        await _run_command_async(
            [
                settings.SEVENZIP_PATH,
                "a",
                str(temporary_archive.resolve()),
                f"@{list_file.resolve()}",
            ],
            cwd=_raw_dir(),
        )
        await _run_command_async(
            [settings.SEVENZIP_PATH, "t", str(temporary_archive.resolve())]
        )
        temporary_archive.replace(archive_path)
    finally:
        list_file.unlink(missing_ok=True)
        temporary_archive.unlink(missing_ok=True)


async def _run_7z_entry_command(
    *,
    command: str,
    archive_path: Path,
    entries: Sequence[str],
) -> None:
    list_file = _tmp_dir() / f"7z-{command}-{uuid.uuid4()}.txt"
    list_file.write_text("\n".join(entries) + "\n")
    try:
        await _run_command_async(
            [
                settings.SEVENZIP_PATH,
                command,
                str(archive_path.resolve()),
                f"@{list_file.resolve()}",
            ],
            cwd=_raw_dir(),
        )
    finally:
        list_file.unlink(missing_ok=True)


async def _upload_release_packages(
    *,
    session: AsyncSession,
    processed_maps: Sequence[_ProcessedMap],
) -> int:
    if not processed_maps:
        return 0

    maps_by_date: dict[date, list[_ProcessedMap]] = defaultdict(list)
    for processed_map in processed_maps:
        maps_by_date[_release_date(processed_map.map_obj.updated_at)].append(processed_map)

    uploaded = 0
    for release_date, maps_for_date in maps_by_date.items():
        package_path = _tmp_dir() / f"maps-release-{release_date.isoformat()}-{uuid.uuid4()}.zip"
        try:
            await asyncio.to_thread(_write_release_zip, package_path, maps_for_date)
            key = f"packages/map-releases/maps-release-{release_date.isoformat()}.zip"
            url = await r2_storage.put_file(
                key=key,
                path=package_path,
                content_type=ZIP_CONTENT_TYPE,
                cache_control=PACKAGE_CACHE_CONTROL,
            )
            row = await session.get(MapPackageRelease, release_date)
            now = get_datetime_utc()
            if row is None:
                row = MapPackageRelease(
                    release_date=release_date,
                    package_key=key,
                    package_url=url,
                    created_at=now,
                )
            row.package_key = key
            row.package_url = url
            row.file_size = package_path.stat().st_size
            row.map_count = len(maps_for_date)
            row.updated_at = now
            session.add(row)
            await session.commit()
            uploaded += 1
        finally:
            package_path.unlink(missing_ok=True)
    return uploaded


def _write_release_zip(package_path: Path, maps_for_date: Sequence[_ProcessedMap]) -> None:
    with zipfile.ZipFile(
        package_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
    ) as archive:
        for processed_map in sorted(maps_for_date, key=lambda item: item.map_obj.name):
            archive.write(
                processed_map.raw_path,
                arcname=_bsp_filename(processed_map.map_obj.name),
            )
