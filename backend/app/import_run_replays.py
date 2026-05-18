from __future__ import annotations

import argparse
import asyncio
import logging
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import py7zr

from app.core.db import async_session_maker
from app.services.run_replay_matcher import match_record_for_run_replay
from app.services.run_replay_parser import RunReplayParseError, parse_run_replay_bytes
from app.services.run_replay_storage import has_run_replay, save_run_replay

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SUPPORTED_INPUT_SUFFIXES = {".replay", ".zip", ".7z"}


@dataclass(frozen=True, slots=True)
class ReplaySource:
    source_name: str
    replay_bytes: bytes


@dataclass(frozen=True, slots=True)
class ImportRunReplaysResult:
    scanned: int = 0
    matched: int = 0
    imported: int = 0
    already_available: int = 0
    unmatched: int = 0
    ambiguous: int = 0
    failed: int = 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import run replays from archives, directories, or files."
    )
    parser.add_argument(
        "inputs",
        metavar="INPUT",
        type=Path,
        nargs="+",
        help="Replay archive, directory, or .replay file to import.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of replay files to process.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and match replay files without writing them.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop immediately when a replay cannot be imported.",
    )
    return parser


@asynccontextmanager
async def _import_session():
    async with async_session_maker() as session:
        yield session


def _iter_directory_inputs(path: Path) -> Iterator[Path]:
    yield from sorted(
        candidate
        for candidate in path.rglob("*")
        if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_INPUT_SUFFIXES
    )


def _iter_zip_replays(path: Path) -> Iterator[ReplaySource]:
    with zipfile.ZipFile(path) as archive:
        replay_infos = [
            info
            for info in archive.infolist()
            if not info.is_dir() and info.filename.lower().endswith(".replay")
        ]
        for info in replay_infos:
            yield ReplaySource(
                source_name=f"{path}:{info.filename}",
                replay_bytes=archive.read(info),
            )


def _iter_7z_replays(path: Path) -> Iterator[ReplaySource]:
    with tempfile.TemporaryDirectory(prefix="run-replay-import-") as temp_dir:
        temp_root = Path(temp_dir)
        with py7zr.SevenZipFile(path, mode="r") as archive:
            replay_names = sorted(
                name for name in archive.getnames() if name.lower().endswith(".replay")
            )
            if replay_names:
                archive.extract(path=temp_root, targets=replay_names)

        for replay_name in replay_names:
            extracted_path = temp_root / replay_name
            if not extracted_path.is_file():
                continue
            yield ReplaySource(
                source_name=f"{path}:{replay_name}",
                replay_bytes=extracted_path.read_bytes(),
            )


def _iter_replay_sources(path: Path) -> Iterator[ReplaySource]:
    if not path.exists():
        raise FileNotFoundError(f"Input path {path} does not exist")
    if path.is_dir():
        for file_path in _iter_directory_inputs(path):
            yield from _iter_replay_sources(file_path)
        return
    if path.suffix.lower() == ".replay":
        yield ReplaySource(source_name=str(path), replay_bytes=path.read_bytes())
        return
    if path.suffix.lower() == ".zip":
        yield from _iter_zip_replays(path)
        return
    if path.suffix.lower() == ".7z":
        yield from _iter_7z_replays(path)
        return
    raise ValueError(f"Unsupported input path {path}")


async def import_run_replays_from_paths(
    input_paths: list[Path],
    *,
    limit: int | None = None,
    dry_run: bool = False,
    fail_fast: bool = False,
) -> ImportRunReplaysResult:
    scanned = 0
    matched = 0
    imported = 0
    already_available = 0
    unmatched = 0
    ambiguous = 0
    failed = 0

    async with _import_session() as session:
        for input_path in input_paths:
            for source in _iter_replay_sources(input_path):
                if limit is not None and scanned >= limit:
                    return ImportRunReplaysResult(
                        scanned=scanned,
                        matched=matched,
                        imported=imported,
                        already_available=already_available,
                        unmatched=unmatched,
                        ambiguous=ambiguous,
                        failed=failed,
                    )
                scanned += 1
                try:
                    replay = parse_run_replay_bytes(
                        data=source.replay_bytes,
                        source_name=source.source_name,
                    )
                    match_result = await match_record_for_run_replay(
                        session=session,
                        replay=replay,
                    )
                    if match_result.is_ambiguous:
                        ambiguous += 1
                        raise ValueError(
                            f"{source.source_name}: multiple records matched replay"
                        )
                    if match_result.match is None:
                        unmatched += 1
                        raise ValueError(
                            f"{source.source_name}: no matching record found"
                        )

                    matched += 1
                    if dry_run:
                        continue

                    record = match_result.match.record
                    if has_run_replay(map_name=replay.map_name, replay_id=record.uuid):
                        already_available += 1
                        continue

                    save_run_replay(
                        map_name=replay.map_name,
                        replay_id=record.uuid,
                        replay_bytes=source.replay_bytes,
                    )
                    imported += 1
                except (
                    FileNotFoundError,
                    RunReplayParseError,
                    ValueError,
                    zipfile.BadZipFile,
                    py7zr.Bad7zFile,
                ) as exc:
                    failed += 1
                    logger.warning("Failed to import %s: %s", source.source_name, exc)
                    if fail_fast:
                        raise

    return ImportRunReplaysResult(
        scanned=scanned,
        matched=matched,
        imported=imported,
        already_available=already_available,
        unmatched=unmatched,
        ambiguous=ambiguous,
        failed=failed,
    )


def main() -> int:
    args = _build_parser().parse_args()
    result = asyncio.run(
        import_run_replays_from_paths(
            args.inputs,
            limit=args.limit,
            dry_run=args.dry_run,
            fail_fast=args.fail_fast,
        )
    )
    logger.info(
        "Run replay import complete: scanned=%s matched=%s imported=%s existing=%s unmatched=%s ambiguous=%s failed=%s",
        result.scanned,
        result.matched,
        result.imported,
        result.already_available,
        result.unmatched,
        result.ambiguous,
        result.failed,
    )
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
