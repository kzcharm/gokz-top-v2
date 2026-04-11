from dataclasses import dataclass

import pytest

from app.models import RecordScope
from app.tasks.build.rating import rebuild_ratings

pytestmark = pytest.mark.asyncio


@dataclass(frozen=True, slots=True)
class _LeaderboardResult:
    selected: int
    created: int
    updated: int


async def test_rebuild_ratings_full_runs_points_then_leaderboard_then_sound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    async def _fake_rebuild_record_pb_points(**kwargs: object) -> int:
        calls.append(("points", kwargs))
        return 123

    async def _fake_rebuild_leaderboard_rows(**kwargs: object) -> _LeaderboardResult:
        calls.append(("leaderboard", kwargs))
        return _LeaderboardResult(selected=10, created=2, updated=8)

    def _fake_play_completion_sound() -> None:
        calls.append("sound")

    monkeypatch.setattr(
        "app.tasks.build.rating.rebuild_record_pb_points",
        _fake_rebuild_record_pb_points,
    )
    monkeypatch.setattr(
        "app.tasks.build.rating.rebuild_leaderboard_rows",
        _fake_rebuild_leaderboard_rows,
    )
    monkeypatch.setattr(
        "app.tasks.build.rating._play_completion_sound",
        _fake_play_completion_sound,
    )

    result = await rebuild_ratings(
        scope_ids=[1, 2],
        scopes=[RecordScope.KZT, RecordScope.SKZ],
        steamid64s=None,
        limit=None,
        full=True,
    )

    assert result.pb_points_updated == 123
    assert result.leaderboard.selected == 10
    assert result.leaderboard.created == 2
    assert result.leaderboard.updated == 8
    assert calls == [
        (
            "points",
            {
                "scopes": [RecordScope.KZT, RecordScope.SKZ],
                "map_names": None,
                "stage": 0,
                "limit": None,
            },
        ),
        (
            "leaderboard",
            {
                "scope_ids": [1, 2],
                "steamid64s": None,
                "limit": None,
                "prioritize_existing_rating": True,
            },
        ),
        "sound",
    ]


def test_play_completion_sound_skips_non_macos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def _fake_run(*args: object, **kwargs: object) -> None:
        del args, kwargs
        nonlocal called
        called = True

    monkeypatch.setattr("app.tasks.build.rating.platform.system", lambda: "Linux")
    monkeypatch.setattr("app.tasks.build.rating.subprocess.run", _fake_run)

    from app.tasks.build.rating import _play_completion_sound

    _play_completion_sound()

    assert called is False


def test_play_completion_sound_logs_failure_without_raising(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr("app.tasks.build.rating.platform.system", lambda: "Darwin")
    caplog.set_level("WARNING")

    class _CompletedProcess:
        returncode = 1
        stderr = "boom"

    monkeypatch.setattr(
        "app.tasks.build.rating.subprocess.run",
        lambda *args, **kwargs: _CompletedProcess(),
    )

    from app.tasks.build.rating import _play_completion_sound

    _play_completion_sound()

    assert "Completion sound failed" in caplog.text
