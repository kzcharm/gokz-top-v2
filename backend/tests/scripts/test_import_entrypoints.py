"""Legacy module entrypoints retain discoverable, non-mutating CLI help."""

import runpy
import sys

import pytest


@pytest.mark.parametrize(
    "module",
    [
        "app.import_v1_users",
        "app.import_v1_player_profile_fields",
        "app.import_v1_player_likes_sessions",
        "app.import_v1_csv_exports",
        "app.import_run_replays",
        "app.import_records_archive",
        "app.import_map_skills",
        "app.import_lj_rooms",
        "app.import_jump_replays_archive",
        "app.backfill_player_session_geo",
        "app.backfill_record_pb_updated_at",
        "app.backfill_recent_wr_events",
    ],
)
def test_import_entrypoint_help_does_not_write(
    module: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", [module, "--help"])
    with pytest.raises(SystemExit) as result:
        runpy.run_module(module, run_name="__main__")
    assert result.value.code == 0
    assert "usage:" in capsys.readouterr().out.lower()
