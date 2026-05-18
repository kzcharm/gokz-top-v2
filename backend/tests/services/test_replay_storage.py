from __future__ import annotations

import uuid
from pathlib import Path

from app.core.config import settings
from app.services.jump_replay_storage import get_jump_replay_path
from app.services.run_replay_storage import (
    get_run_replay_path,
    normalize_run_replay_map_dir,
)


def test_get_jump_replay_path_uses_jump_subdirectory() -> None:
    jumpstat_id = uuid.uuid4()

    assert get_jump_replay_path(jumpstat_id=jumpstat_id) == (
        settings.REPLAY_STORAGE_DIR / "jumps" / f"{jumpstat_id}.replay"
    )


def test_get_run_replay_path_uses_normalized_map_name_subdirectory() -> None:
    replay_id = uuid.uuid4()

    assert get_run_replay_path(map_name=" KZ Test/Map ", replay_id=replay_id) == (
        settings.REPLAY_STORAGE_DIR
        / "runs"
        / Path("kz_test_map")
        / f"{replay_id}.replay"
    )


def test_normalize_run_replay_map_dir_rejects_blank_values() -> None:
    try:
        normalize_run_replay_map_dir("   ")
    except ValueError as exc:
        assert str(exc) == "map_name must not be blank"
    else:
        raise AssertionError("Expected normalize_run_replay_map_dir to reject blanks")
