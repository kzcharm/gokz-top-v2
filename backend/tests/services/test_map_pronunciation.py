import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio
from elevenlabs.core.api_error import ApiError
from httpx import AsyncClient
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import async_session_maker
from app.models import Map, MapPronunciation, ScheduledTaskState, get_datetime_utc
from app.services import map_pronunciation as service
from app.services import map_pronunciation_worker as worker


@pytest.fixture(autouse=True)
def pronunciation_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ELEVENLABS_API_KEY", "test-only")
    monkeypatch.setattr(settings, "R2_ACCOUNT_ID", "test-account")
    monkeypatch.setattr(settings, "R2_ACCESS_KEY_ID", "test-access")
    monkeypatch.setattr(settings, "R2_SECRET_ACCESS_KEY", "test-secret")
    monkeypatch.setattr(settings, "R2_BUCKET_NAME", "test-bucket")
    monkeypatch.setattr(settings, "R2_PUBLIC_BASE_URL", "https://audio.example.test")


@pytest_asyncio.fixture
async def map_obj(db: AsyncSession) -> Map:
    map_obj = Map(id=991700, name="kz_21loop_final_fix", validated=True)
    db.add(map_obj)
    await db.commit()
    return map_obj


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("bkz_hellokitty_v2", "hellokitty"),
        ("kz_alouette_fix", "alouette"),
        ("kz_21loop_final_fix", "21loop final"),
        ("bkz_cauz_final", "cauz final"),
        ("kz_example_v2_final", "example final"),
        ("KZPRO_Example_V2_FINAL2_FIX3", "Example FINAL2"),
        ("xc_2seasons_winter_final", "2seasons winter final"),
        ("vnl_name_easy_fix", "name easy"),
        ("skz_name_hard_v2go", "name hard"),
        ("kz_name_short_csgo", "name short"),
        ("kz_name_od2_b03_c02_gfix_go", "name"),
        ("kz_fix_the_map", "fix the map"),
        ("custom_name_final2", "custom name final2"),
        (" kz__hello___world__ ", "hello world"),
        ("kz_final_boss_fix", "final boss"),
        ("kz_", ""),
        ("___", ""),
        ("", ""),
    ],
)
def test_spoken_names(name: str, expected: str) -> None:
    assert service.spoken_map_name(name) == expected


def test_fingerprint_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    first = service.generation_fingerprint("hello")
    assert first == service.generation_fingerprint("hello")
    assert first != service.generation_fingerprint("world")
    monkeypatch.setattr(settings, "ELEVENLABS_VOICE_ID", "other")
    assert first != service.generation_fingerprint("hello")
    monkeypatch.setattr(settings, "ELEVENLABS_API_KEY", None)
    assert not service.is_configured()


@pytest.mark.asyncio
async def test_public_api_is_lazy_idempotent_and_cached(
    client: AsyncClient, db: AsyncSession, map_obj: Map
) -> None:
    url = f"/v1/maps/{map_obj.id}/pronunciation"
    response = await client.get(url)
    assert response.json() == {
        "status": "missing",
        "spoken_text": "21loop final",
        "audio_url": None,
    }
    assert await db.get(MapPronunciation, map_obj.id) is None
    for _ in range(2):
        response = await client.post(url)
        assert response.status_code == 202
        assert response.json()["status"] == "pending"
    rows = (
        await db.exec(
            select(MapPronunciation).where(MapPronunciation.map_id == map_obj.id)
        )
    ).all()
    assert len(rows) == 1
    row = rows[0]
    row.status = "ready"
    row.object_key = "maps/pronunciations/example.mp3"
    db.add(row)
    await db.commit()
    for method in (client.post, client.get):
        response = await method(url)
        assert response.status_code == 200
        assert (
            response.json()["audio_url"]
            == "https://audio.example.test/maps/pronunciations/example.mp3"
        )
    assert row.attempts == 0


@pytest.mark.asyncio
async def test_public_api_unavailable_and_unknown(
    client: AsyncClient, map_obj: Map, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ELEVENLABS_API_KEY", None)
    for method in (client.post, client.get):
        assert (await method(f"/v1/maps/{map_obj.id}/pronunciation")).status_code == 503
        assert (await method("/v1/maps/999999999/pronunciation")).status_code == 404


@pytest.mark.asyncio
async def test_force_rename_and_empty_name(db: AsyncSession, map_obj: Map) -> None:
    row = await service.request_pronunciation(session=db, map_obj=map_obj)
    row.status = "failed"
    row.attempts = 5
    db.add(row)
    await db.commit()
    assert (
        await service.request_pronunciation(session=db, map_obj=map_obj)
    ).status == "failed"
    row = await service.request_pronunciation(session=db, map_obj=map_obj, force=True)
    assert row.status == "pending" and row.attempts == 0
    map_obj.name = "kz_new_final"
    db.add(map_obj)
    assert service.public_pronunciation(map_obj=map_obj, row=row).status == "missing"
    row = await service.request_pronunciation(session=db, map_obj=map_obj)
    assert row.spoken_text == "new final"
    map_obj.name = "kz_"
    db.add(map_obj)
    row = await service.request_pronunciation(session=db, map_obj=map_obj)
    assert row.status == "failed" and row.last_error == "empty_spoken_name"


@pytest.mark.asyncio
async def test_generation_and_restart_recovery(
    db: AsyncSession, map_obj: Map, monkeypatch: pytest.MonkeyPatch
) -> None:
    generate = AsyncMock(return_value=b"test-mp3")
    upload = AsyncMock(return_value="https://audio.example.test/result.mp3")
    monkeypatch.setattr(service, "generate_audio", generate)
    monkeypatch.setattr(service.r2_storage, "put_object", upload)
    row = await service.request_pronunciation(session=db, map_obj=map_obj)
    row.status = "generating"  # A worker was interrupted after claiming this job.
    row.attempts = 1
    db.add(row)
    await db.commit()
    assert await worker.process_next_job(session=db)
    assert row.status == "ready" and row.attempts == 2
    generate.assert_awaited_once_with("21loop final")
    assert upload.call_args.kwargs["content_type"] == "audio/mpeg"
    assert upload.call_args.kwargs["body"] == b"test-mp3"
    assert row.object_key and row.fingerprint in row.object_key
    assert not await worker.process_next_job(session=db)


@pytest.mark.parametrize(
    ("error", "expected", "paused"),
    [
        (ApiError(status_code=429, body={"detail": "busy"}), "pending", False),
        (ApiError(status_code=503, body=None), "pending", False),
        (ApiError(status_code=401, body="private-provider-data"), "pending", True),
        (ApiError(status_code=402, body=None), "pending", True),
        (ApiError(status_code=403, body=None), "pending", True),
        (
            ApiError(status_code=400, body={"detail": {"status": "quota_exceeded"}}),
            "pending",
            True,
        ),
        (ApiError(status_code=422, body="bad request"), "failed", False),
        (ValueError("private-provider-data"), "pending", False),
    ],
)
@pytest.mark.asyncio
async def test_generation_failures(
    db: AsyncSession,
    map_obj: Map,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected: str,
    paused: bool,
) -> None:
    monkeypatch.setattr(service, "generate_audio", AsyncMock(side_effect=error))
    row = await service.request_pronunciation(session=db, map_obj=map_obj)
    await db.commit()
    await service.process_job(session=db, row=row)
    assert row.status == expected and row.attempts == 1
    assert row.last_error and "private-provider-data" not in row.last_error
    assert row.next_attempt_at > get_datetime_utc()
    state = await db.get(ScheduledTaskState, service.TASK_NAME)
    assert bool(state and state.last_error) == paused
    assert not await worker.process_next_job(session=db)


@pytest.mark.asyncio
async def test_storage_failure_and_retry_limit(
    db: AsyncSession, map_obj: Map, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "generate_audio", AsyncMock(return_value=b"test"))
    monkeypatch.setattr(
        service.r2_storage,
        "put_object",
        AsyncMock(side_effect=RuntimeError("upload failed")),
    )
    row = await service.request_pronunciation(session=db, map_obj=map_obj)
    row.attempts = settings.MAP_PRONUNCIATION_MAX_ATTEMPTS - 1
    db.add(row)
    await db.commit()
    await service.process_job(session=db, row=row)
    assert row.status == "failed" and row.object_key is None
    row.status = "generating"
    db.add(row)
    await db.commit()
    await service.process_job(session=db, row=row)
    assert row.status == "failed" and row.last_error == "retry_limit_reached"


@pytest.mark.asyncio
async def test_sdk_request_matches_voice_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_client = httpx.AsyncClient
    requests = []

    def handle(request: httpx.Request) -> httpx.Response:
        import json

        requests.append(json.loads(request.content))
        assert request.url.params["output_format"] == "mp3_44100_128"
        assert request.url.path.endswith("/DODLEQrClDo8wCz460ld")
        return httpx.Response(
            200, content=b"mp3", headers={"content-type": "audio/mpeg"}
        )

    monkeypatch.setattr(
        service.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(
            transport=httpx.MockTransport(handle), **kwargs
        ),
    )
    assert await service.generate_audio("21loop final") == b"mp3"
    assert requests[0]["text"] == "21loop final"
    assert requests[0]["model_id"] == "eleven_v4"
    assert requests[0]["voice_settings"]["clone_strength"] == 0


@pytest.mark.asyncio
async def test_concurrent_requests_create_one_job() -> None:
    map_id = 991701
    async with async_session_maker() as session:
        await session.exec(delete(Map).where(Map.id == map_id))
        session.add(Map(id=map_id, name="kz_concurrent_final", validated=True))
        await session.commit()
    try:

        async def request() -> None:
            async with async_session_maker() as session:
                map_obj = await session.get(Map, map_id)
                assert map_obj
                await service.request_pronunciation(session=session, map_obj=map_obj)
                await session.commit()

        await asyncio.gather(request(), request(), request())
        async with async_session_maker() as session:
            rows = (
                await session.exec(
                    select(MapPronunciation).where(MapPronunciation.map_id == map_id)
                )
            ).all()
            assert len(rows) == 1 and rows[0].attempts == 0
    finally:
        async with async_session_maker() as session:
            await session.exec(delete(Map).where(Map.id == map_id))
            await session.commit()


@pytest.mark.asyncio
async def test_failed_job_is_not_requeued_by_click(
    db: AsyncSession, map_obj: Map
) -> None:
    row = await service.request_pronunciation(session=db, map_obj=map_obj)
    row.status = "failed"
    row.next_attempt_at = get_datetime_utc() - timedelta(seconds=1)
    db.add(row)
    await db.commit()
    assert not await worker.process_next_job(session=db)
    assert (
        await service.request_pronunciation(session=db, map_obj=map_obj)
    ).status == "failed"


@pytest.mark.asyncio
async def test_paused_queue_fails_fast_but_keeps_ready_audio(
    client: AsyncClient, db: AsyncSession, map_obj: Map
) -> None:
    row = await service.request_pronunciation(session=db, map_obj=map_obj)
    db.add(
        ScheduledTaskState(
            task_name=service.TASK_NAME, last_error="provider_credentials_or_credits"
        )
    )
    await db.commit()
    for method in (client.get, client.post):
        result = await method(f"/v1/maps/{map_obj.id}/pronunciation")
        assert result.status_code == 200 and result.json()["status"] == "failed"
    assert row.status == "pending"
    row.status = "ready"
    row.object_key = "maps/pronunciations/ready.mp3"
    db.add(row)
    await db.commit()
    assert (await client.get(f"/v1/maps/{map_obj.id}/pronunciation")).json()[
        "status"
    ] == "ready"


@pytest.mark.asyncio
async def test_regeneration_during_generation_cannot_publish_old_clip(
    db: AsyncSession, map_obj: Map, monkeypatch: pytest.MonkeyPatch
) -> None:
    map_id = map_obj.id
    row = await service.request_pronunciation(session=db, map_obj=map_obj)
    await db.commit()

    async def replace_job(_text: str) -> bytes:
        await service.request_pronunciation(session=db, map_obj=map_obj, force=True)
        await db.commit()
        return b"superseded"

    monkeypatch.setattr(service, "generate_audio", replace_job)
    monkeypatch.setattr(service.r2_storage, "put_object", AsyncMock())
    await service.process_job(session=db, row=row)
    refreshed = await db.get(MapPronunciation, map_id, populate_existing=True)
    assert refreshed and refreshed.status == "pending" and refreshed.object_key is None


def test_storage_http_error_classification() -> None:
    for status, retryable, pause in [
        (403, False, True),
        (429, True, False),
        (503, True, False),
        (400, False, False),
    ]:
        error = httpx.HTTPStatusError(
            "private",
            request=httpx.Request("PUT", "https://storage.example"),
            response=httpx.Response(status),
        )
        _, actual_retry, actual_pause = service.error_kind(error)
        assert (actual_retry, actual_pause) == (retryable, pause)


@pytest.mark.parametrize("acquired", [True, False])
@pytest.mark.asyncio
async def test_runner_holds_advisory_lock(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, acquired: bool
) -> None:
    cursor = AsyncMock()
    cursor.__aenter__.return_value = cursor
    cursor.fetchone.return_value = (acquired,)
    connection = MagicMock()
    connection.__aenter__ = AsyncMock(return_value=connection)
    connection.__aexit__ = AsyncMock()
    connection.cursor.return_value = cursor
    monkeypatch.setattr(
        worker.psycopg.AsyncConnection, "connect", AsyncMock(return_value=connection)
    )
    process = AsyncMock(return_value=True)
    monkeypatch.setattr(worker, "process_next_job", process)

    @asynccontextmanager
    async def session_context():
        yield db

    async def finish(_seconds: float) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(worker, "async_session_maker", session_context)
    monkeypatch.setattr(worker.asyncio, "sleep", finish)
    with pytest.raises(asyncio.CancelledError):
        await worker.run_map_pronunciation_runner()
    assert process.await_count == int(acquired)
    cursor.execute.assert_awaited_once_with(
        "SELECT pg_try_advisory_lock(%s)", (worker.LOCK_ID,)
    )
    connection.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
async def test_runner_unconfigured_and_connection_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connect = AsyncMock(side_effect=RuntimeError("private"))
    monkeypatch.setattr(worker.psycopg.AsyncConnection, "connect", connect)

    async def finish(_seconds: float) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(worker.asyncio, "sleep", finish)
    monkeypatch.setattr(worker, "is_configured", lambda: False)
    with pytest.raises(asyncio.CancelledError):
        await worker.run_map_pronunciation_runner()
    connect.assert_not_awaited()
    monkeypatch.setattr(worker, "is_configured", lambda: True)
    with pytest.raises(asyncio.CancelledError):
        await worker.run_map_pronunciation_runner()
    connect.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_runner_cancels_cleanly() -> None:
    await worker.stop_map_pronunciation_runner(None)

    async def wait_forever() -> None:
        await asyncio.Future()

    task = asyncio.create_task(wait_forever())
    await worker.stop_map_pronunciation_runner(task)
    assert task.cancelled()
