from __future__ import annotations

import uuid
from pathlib import Path

from app.services.replay_storage import (
    delete_replay,
    get_replay_path,
    load_replay,
    save_replay,
)


def get_jump_replay_path(*, jumpstat_id: uuid.UUID) -> Path:
    return get_replay_path(namespace="jumps", replay_id=jumpstat_id)


def load_jump_replay(*, jumpstat_id: uuid.UUID) -> bytes:
    return load_replay(namespace="jumps", replay_id=jumpstat_id)


def save_jump_replay(*, jumpstat_id: uuid.UUID, replay_bytes: bytes) -> Path:
    return save_replay(namespace="jumps", replay_id=jumpstat_id, replay_bytes=replay_bytes)


def delete_jump_replay(*, jumpstat_id: uuid.UUID) -> bool:
    return delete_replay(namespace="jumps", replay_id=jumpstat_id)
