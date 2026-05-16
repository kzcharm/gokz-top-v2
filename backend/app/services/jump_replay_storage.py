from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

from app.core.config import settings


def get_jump_replay_path(*, jumpstat_id: uuid.UUID) -> Path:
    return (
        settings.JUMP_REPLAY_STORAGE_DIR / jumpstat_id.hex[:2] / f"{jumpstat_id}.replay"
    )


def save_jump_replay(*, jumpstat_id: uuid.UUID, replay_bytes: bytes) -> Path:
    destination = get_jump_replay_path(jumpstat_id=jumpstat_id)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        dir=destination.parent,
        prefix=f"{jumpstat_id}.",
        suffix=".tmp",
        delete=False,
    ) as stream:
        stream.write(replay_bytes)
        temp_path = Path(stream.name)

    os.replace(temp_path, destination)
    return destination
