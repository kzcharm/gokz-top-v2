from __future__ import annotations

import argparse
import asyncio
import logging
import uuid
import zipfile
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from app import crud
from app.core.db import async_session_maker
from app.services.jump_replay_parser import (
    JumpReplayParseError,
    parse_jump_replay_bytes,
)
from app.services.jumpstat_ingest import import_jump_replay

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ImportJumpReplayArchiveResult:
    scanned: int = 0
    inserted: int = 0
    deduped: int = 0
    failed: int = 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import jump replays from a zip archive."
    )
    parser.add_argument(
        "--archive", type=Path, required=True, help="Path to jumps zip archive."
    )
    parser.add_argument(
        "--server-group",
        type=str,
        required=True,
        help="Server group custom_id or exact name.",
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
        help="Parse and validate archive entries without inserting rows.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop immediately when a replay cannot be imported.",
    )
    return parser


async def _resolve_server_group_id(*, identifier: str) -> tuple[str, uuid.UUID]:
    async with async_session_maker() as session:
        groups = await crud.get_server_groups_by_custom_id_or_name(
            session=session,
            identifier=identifier,
        )
        if not groups:
            raise ValueError(f"Server group {identifier!r} was not found")
        if len(groups) > 1:
            raise ValueError(f"Server group {identifier!r} is ambiguous")
        return groups[0].name, groups[0].id


def iter_replay_archive_members(path: Path) -> list[zipfile.ZipInfo]:
    with zipfile.ZipFile(path) as archive:
        infos = [
            info
            for info in archive.infolist()
            if not info.is_dir() and info.filename.lower().endswith(".replay")
        ]
    return infos


@asynccontextmanager
async def _import_session():
    async with async_session_maker() as session:
        yield session


async def import_jump_replays_archive_from_path(
    archive_path: Path,
    *,
    server_group: str,
    limit: int | None = None,
    dry_run: bool = False,
    fail_fast: bool = False,
) -> ImportJumpReplayArchiveResult:
    group_name, group_id = await _resolve_server_group_id(identifier=server_group)
    logger.info("Resolved server group %s -> %s", group_name, group_id)

    scanned = 0
    inserted = 0
    deduped = 0
    failed = 0

    with zipfile.ZipFile(archive_path) as archive:
        replay_infos = [
            info
            for info in archive.infolist()
            if not info.is_dir() and info.filename.lower().endswith(".replay")
        ]
        if limit is not None:
            replay_infos = replay_infos[:limit]

        async with _import_session() as session:
            group = await crud.get_server_group_by_id(
                session=session, group_id=group_id
            )
            if group is None:
                raise ValueError(f"Resolved server group {group_id} no longer exists")

            for info in replay_infos:
                scanned += 1
                try:
                    replay_bytes = archive.read(info)
                    if dry_run:
                        parse_jump_replay_bytes(
                            data=replay_bytes,
                            source_name=info.filename,
                        )
                        continue

                    result = await import_jump_replay(
                        session=session,
                        group=group,
                        replay_bytes=replay_bytes,
                        source_name=info.filename,
                    )
                    if result.created:
                        inserted += 1
                    else:
                        deduped += 1
                except (JumpReplayParseError, ValueError, zipfile.BadZipFile) as exc:
                    failed += 1
                    logger.warning("Failed to import %s: %s", info.filename, exc)
                    if fail_fast:
                        raise

    return ImportJumpReplayArchiveResult(
        scanned=scanned,
        inserted=inserted,
        deduped=deduped,
        failed=failed,
    )


def main() -> int:
    args = _build_parser().parse_args()
    result = asyncio.run(
        import_jump_replays_archive_from_path(
            args.archive,
            server_group=args.server_group,
            limit=args.limit,
            dry_run=args.dry_run,
            fail_fast=args.fail_fast,
        )
    )
    logger.info(
        "Jump replay import complete: scanned=%s inserted=%s deduped=%s failed=%s",
        result.scanned,
        result.inserted,
        result.deduped,
        result.failed,
    )
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
