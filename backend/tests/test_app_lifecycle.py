"""Application startup, shutdown and versioned API documentation."""

import asyncio
import importlib

import pytest
from httpx import AsyncClient

main = importlib.import_module("app.main")


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True])
async def test_lifespan_starts_enabled_workers_and_cancels_all_tasks(
    monkeypatch: pytest.MonkeyPatch,
    enabled: bool,
) -> None:
    started = []
    stopped = []
    worker_names = [
        (None, "listen_for_server_updates", "stop_listener"),
        (None, "listen_for_recent_record_updates", "stop_record_listener"),
        (
            None,
            "listen_for_player_steam_profile_updates",
            "stop_player_steam_profile_listener",
        ),
        (
            "RUN_SERVER_STATUS_COLLECTOR_IN_APP",
            "run_server_query_collector_in_app",
            "stop_collector",
        ),
        (
            "RUN_GLOBALAPI_SYNC_RUNNER_IN_APP",
            "run_globalapi_sync_runner_in_app",
            "stop_globalapi_sync_runner",
        ),
        (
            "RUN_DAILY_RANK_PIPELINE_TASK_RUNNER_IN_APP",
            "run_daily_rank_pipeline_runner_in_app",
            "stop_daily_rank_pipeline_runner",
        ),
        (
            "RUN_PLAYER_SESSION_TIMEOUT_RUNNER_IN_APP",
            "run_player_session_timeout_runner_in_app",
            "stop_player_session_timeout_runner",
        ),
        (
            "RUN_LIVE_STREAM_RUNNER_IN_APP",
            "run_live_stream_runner_in_app",
            "stop_live_stream_runner",
        ),
        (
            "RUN_MEDIA_SYNC_RUNNER_IN_APP",
            "run_media_sync_runner_in_app",
            "stop_media_sync_runner",
        ),
        (
            "RUN_JUMP_REPLAY_CLEANUP_RUNNER_IN_APP",
            "run_jump_replay_cleanup_runner_in_app",
            "stop_jump_replay_cleanup_runner",
        ),
        (
            "RUN_MAP_FILE_DISTRIBUTION_RUNNER_IN_APP",
            "run_map_file_distribution_runner",
            "stop_map_file_distribution_runner",
        ),
    ]

    def worker(name):
        async def run():
            started.append(name)
            await asyncio.Event().wait()

        return run

    async def stop(task):
        if task is not None:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            stopped.append(task)

    for flag, runner, stopper in worker_names:
        if flag:
            monkeypatch.setattr(main.settings, flag, enabled)
        monkeypatch.setattr(main, runner, worker(runner))
        monkeypatch.setattr(main, stopper, stop)
    async with main.lifespan(main.app):
        await asyncio.sleep(0)
        assert len(started) == (len(worker_names) if enabled else 3)
    assert len(stopped) == len(started)
    assert all(task.cancelled() for task in stopped)


@pytest.mark.asyncio
async def test_versioned_openapi_and_swagger_are_available(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main, "_openapi_v0_schema", None)
    monkeypatch.setattr(main, "_openapi_v1_schema", None)
    for path, version in [("/v0/openapi.json", "v0"), ("/v1/openapi.json", "v1")]:
        response = await client.get(path)
        assert response.status_code == 200
        schema = response.json()
        assert schema["info"]["version"] == version
        assert schema["paths"]
        assert all(route.startswith(f"/{version}/") for route in schema["paths"])
        assert (await client.get(path)).json() == schema
    docs = await client.get("/docs")
    assert docs.status_code == 200
    assert "/v0/openapi.json" in docs.text and "/v1/openapi.json" in docs.text
    assert "SwaggerUIBundle" in docs.text
    formatted = main._format_openapi_tags(
        {"paths": {"/route": {"get": {"tags": ["server_status", 3]}, "parameters": []}}}
    )
    assert formatted["paths"]["/route"]["get"]["tags"] == ["Server Status", 3]
