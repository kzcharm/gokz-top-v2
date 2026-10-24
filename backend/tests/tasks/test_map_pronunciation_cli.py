from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from typer.testing import CliRunner

from app import cli
from app.core import db as database
from app.models import Map, ScheduledTaskState
from app.services import map_pronunciation as service
from app.services import map_pronunciation_worker as worker


def test_pronunciation_cli_regeneration_and_missing_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock()
    map_obj = Map(id=991700, name="kz_example_final")
    session.get = AsyncMock(return_value=map_obj)
    session.commit = AsyncMock()

    @asynccontextmanager
    async def session_context():
        yield session

    request = AsyncMock()
    monkeypatch.setattr(database, "async_session_maker", session_context)
    monkeypatch.setattr(service, "request_pronunciation", request)
    result = CliRunner().invoke(cli.app, ["map-pronunciations", "regenerate", "991700"])
    assert result.exit_code == 0
    assert "Queued pronunciation for map 991700" in result.output
    request.assert_awaited_once_with(session=session, map_obj=map_obj, force=True)
    session.commit.assert_awaited_once()
    session.get.return_value = None
    result = CliRunner().invoke(cli.app, ["map-pronunciations", "regenerate", "991700"])
    assert result.exit_code != 0 and "Map not found" in result.output


@pytest.mark.parametrize("has_state", [True, False])
def test_pronunciation_cli_resumes_queue(
    monkeypatch: pytest.MonkeyPatch, has_state: bool
) -> None:
    session = MagicMock()
    state = ScheduledTaskState(
        task_name=service.TASK_NAME, last_error="provider_credentials_or_credits"
    )
    session.get = AsyncMock(return_value=state if has_state else None)
    session.commit = AsyncMock()

    @asynccontextmanager
    async def session_context():
        yield session

    monkeypatch.setattr(database, "async_session_maker", session_context)
    result = CliRunner().invoke(cli.app, ["map-pronunciations", "resume"])
    assert result.exit_code == 0
    assert "generation resumed" in result.output
    if has_state:
        assert state.last_error is None
        session.commit.assert_awaited_once()
    else:
        session.commit.assert_not_awaited()


def test_pronunciation_cli_runs_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    run = AsyncMock()
    monkeypatch.setattr(worker, "run_map_pronunciation_runner", run)
    result = CliRunner().invoke(cli.app, ["map-pronunciations", "run-worker"])
    assert result.exit_code == 0
    run.assert_awaited_once()


def test_player_pronunciation_cli_regeneration(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.models import Player
    from app.services import player_pronunciation

    session = MagicMock()
    player = Player(steamid64=76561198991700001, name="Player", alias="Alias")
    session.get = AsyncMock(return_value=player)
    session.commit = AsyncMock()

    @asynccontextmanager
    async def session_context():
        yield session

    request = AsyncMock()
    monkeypatch.setattr(database, "async_session_maker", session_context)
    monkeypatch.setattr(player_pronunciation, "request_player_pronunciation", request)
    result = CliRunner().invoke(
        cli.app, ["player-pronunciations", "regenerate", str(player.steamid64)]
    )
    assert result.exit_code == 0 and "Queued pronunciation for player" in result.output
    request.assert_awaited_once_with(session=session, player=player, force=True)
    session.get.return_value = None
    result = CliRunner().invoke(
        cli.app, ["player-pronunciations", "regenerate", str(player.steamid64)]
    )
    assert result.exit_code != 0 and "Player not found" in result.output
