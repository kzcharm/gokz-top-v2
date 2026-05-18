from __future__ import annotations

import re
import uuid
from pathlib import Path

from app.services.replay_storage import (
    get_replay_path,
    has_replay,
    load_replay,
    save_replay,
)


def normalize_run_replay_map_dir(map_name: str) -> str:
    normalized = re.sub(r"[^a-z0-9._-]+", "_", map_name.strip().lower()).strip("_")
    if not normalized:
        raise ValueError("map_name must not be blank")
    return normalized


def get_run_replay_path(*, map_name: str, replay_id: uuid.UUID) -> Path:
    return get_replay_path(
        namespace="runs",
        relative_dir=Path(normalize_run_replay_map_dir(map_name)),
        replay_id=replay_id,
    )


def load_run_replay(*, map_name: str, replay_id: uuid.UUID) -> bytes:
    return load_replay(
        namespace="runs",
        relative_dir=Path(normalize_run_replay_map_dir(map_name)),
        replay_id=replay_id,
    )


def has_run_replay(*, map_name: str, replay_id: uuid.UUID) -> bool:
    return has_replay(
        namespace="runs",
        relative_dir=Path(normalize_run_replay_map_dir(map_name)),
        replay_id=replay_id,
    )


def save_run_replay(*, map_name: str, replay_id: uuid.UUID, replay_bytes: bytes) -> Path:
    return save_replay(
        namespace="runs",
        relative_dir=Path(normalize_run_replay_map_dir(map_name)),
        replay_id=replay_id,
        replay_bytes=replay_bytes,
    )
