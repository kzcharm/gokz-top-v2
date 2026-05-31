from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from typing import Literal

from app.core.config import settings

ReplayNamespace = Literal["jumps", "runs"]


def get_replay_path(
    *,
    namespace: ReplayNamespace,
    replay_id: uuid.UUID,
    relative_dir: Path | None = None,
) -> Path:
    base_dir = settings.REPLAY_STORAGE_DIR / namespace
    if relative_dir is not None:
        base_dir = base_dir / relative_dir
    return base_dir / f"{replay_id}.replay"


def load_replay(
    *,
    namespace: ReplayNamespace,
    replay_id: uuid.UUID,
    relative_dir: Path | None = None,
) -> bytes:
    return get_replay_path(
        namespace=namespace,
        replay_id=replay_id,
        relative_dir=relative_dir,
    ).read_bytes()


def has_replay(
    *,
    namespace: ReplayNamespace,
    replay_id: uuid.UUID,
    relative_dir: Path | None = None,
) -> bool:
    return get_replay_path(
        namespace=namespace,
        replay_id=replay_id,
        relative_dir=relative_dir,
    ).exists()


def save_replay(
    *,
    namespace: ReplayNamespace,
    replay_id: uuid.UUID,
    replay_bytes: bytes,
    relative_dir: Path | None = None,
) -> Path:
    destination = get_replay_path(
        namespace=namespace,
        replay_id=replay_id,
        relative_dir=relative_dir,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        dir=destination.parent,
        prefix=f"{replay_id}.",
        suffix=".tmp",
        delete=False,
    ) as stream:
        stream.write(replay_bytes)
        temp_path = Path(stream.name)

    os.replace(temp_path, destination)
    return destination


def delete_replay(
    *,
    namespace: ReplayNamespace,
    replay_id: uuid.UUID,
    relative_dir: Path | None = None,
) -> bool:
    path = get_replay_path(
        namespace=namespace,
        replay_id=replay_id,
        relative_dir=relative_dir,
    )
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True
