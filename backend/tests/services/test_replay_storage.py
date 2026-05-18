from __future__ import annotations

import uuid
from pathlib import Path

from app.core.config import settings
from app.services.jump_replay_storage import get_jump_replay_path
from app.services.run_replay_storage import (
    get_run_replay_path,
    has_run_replay,
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


def test_has_run_replay_checks_expected_path(tmp_path, monkeypatch) -> None:
    replay_id = uuid.uuid4()
    monkeypatch.setattr(settings, "REPLAY_STORAGE_DIR", tmp_path)

    assert has_run_replay(map_name="kz_test_map", replay_id=replay_id) is False

    replay_path = get_run_replay_path(map_name="kz_test_map", replay_id=replay_id)
    replay_path.parent.mkdir(parents=True, exist_ok=True)
    replay_path.write_bytes(b"sample")

    assert has_run_replay(map_name="kz_test_map", replay_id=replay_id) is True
