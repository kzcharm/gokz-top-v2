from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.models import KZMode, ReplayListQuery
from app.services.run_replay_parser import RunReplayParseError, parse_run_replay_bytes
from app.services.run_replay_storage import normalize_run_replay_map_dir


@dataclass(frozen=True, slots=True)
class RunReplayListEntry:
    record_uuid: uuid.UUID
    map_name: str
    steamid64: int
    mode: KZMode
    stage: int
    teleports: int
    time_seconds: float


def _iter_replay_paths(*, map_name: str | None) -> list[Path]:
    runs_dir = settings.REPLAY_STORAGE_DIR / "runs"
    if not runs_dir.exists():
        return []

    if map_name is not None:
        replay_dir = runs_dir / normalize_run_replay_map_dir(map_name)
        if not replay_dir.exists():
            return []
        return sorted(replay_dir.glob("*.replay"))

    return sorted(runs_dir.rglob("*.replay"))


def _matches_query(*, entry: RunReplayListEntry, query: ReplayListQuery) -> bool:
    if query.steamid64 is not None and entry.steamid64 != query.steamid64:
        return False
    if query.mode is not None and entry.mode != query.mode:
        return False
    if entry.stage != query.stage:
        return False
    if query.teleports is not None and entry.teleports != query.teleports:
        return False
    return True


def list_run_replay_record_uuids(*, query: ReplayListQuery) -> list[uuid.UUID]:
    entries: list[RunReplayListEntry] = []
    for replay_path in _iter_replay_paths(map_name=query.map_name):
        try:
            record_uuid = uuid.UUID(replay_path.stem)
        except ValueError:
            continue

        try:
            parsed = parse_run_replay_bytes(
                data=replay_path.read_bytes(),
                source_name=str(replay_path),
            )
        except (OSError, RunReplayParseError):
            continue

        entry = RunReplayListEntry(
            record_uuid=record_uuid,
            map_name=parsed.map_name,
            steamid64=parsed.steamid64,
            mode=parsed.mode,
            stage=parsed.course,
            teleports=parsed.teleports_used,
            time_seconds=float(parsed.time),
        )
        if _matches_query(entry=entry, query=query):
            entries.append(entry)

    entries.sort(key=lambda entry: (entry.time_seconds, entry.record_uuid))
    return [entry.record_uuid for entry in entries]
