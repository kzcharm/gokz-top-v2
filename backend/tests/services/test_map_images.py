import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import settings
from app.services import map_images

WEBP = b"RIFF\x04\x00\x00\x00WEBPtest"
COMMIT = "a" * 40
TREE = "b" * 40


def blob_sha(content: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(content)).encode() + b"\0" + content,
        usedforsecurity=False,
    ).hexdigest()


@pytest.fixture
def storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "MAP_IMAGE_STORAGE_DIR", tmp_path)
    monkeypatch.setattr(
        map_images,
        "LOCK_ID",
        int.from_bytes(
            hashlib.sha256(str(tmp_path).encode()).digest()[:8], "big", signed=True
        ),
    )
    return tmp_path


def transport_for(files: dict[str, bytes], requests: list[str]) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url.path.endswith("/commits/public"):
            return httpx.Response(
                200, json={"sha": COMMIT, "commit": {"tree": {"sha": TREE}}}
            )
        if "/git/trees/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "truncated": False,
                    "tree": [
                        {
                            "path": f"webp/{name}.webp",
                            "type": "blob",
                            "sha": blob_sha(content),
                        }
                        for name, content in files.items()
                    ],
                },
            )
        name = request.url.path.split("/webp/", 1)[1][:-5]
        assert f"/{COMMIT}/webp/" in request.url.path
        return httpx.Response(200, content=files[name])

    return httpx.MockTransport(handle)


@pytest.mark.asyncio
async def test_initial_incremental_repair_and_deletion(storage: Path) -> None:
    requests: list[str] = []
    files = {
        "kz_alpha": WEBP,
        "kz_space (1)": WEBP,
        "medium/kz_alpha": WEBP,
        "kz_trailing ": WEBP,
    }
    async with httpx.AsyncClient(transport=transport_for(files, requests)) as client:
        result = await map_images.sync_images(client)
        assert result.total == result.downloaded == 4
        assert (storage / "kz_alpha.webp").read_bytes() == WEBP
        assert map_images.read_manifest().last_success_at is not None
        assert map_images.local_image_url("kz_space (1)").endswith(
            "kz_space%20%281%29.webp"
        )
        assert (storage / "medium/kz_alpha.webp").read_bytes() == WEBP
        assert (storage / "kz_trailing .webp").read_bytes() == WEBP
        requests.clear()
        assert (await map_images.sync_images(client)).downloaded == 0
        assert len(requests) == 2
        (storage / "kz_alpha.webp").unlink()
        assert (await map_images.sync_images(client)).downloaded == 1
        files["kz_alpha"] = WEBP + b"updated"
        del files["kz_space (1)"]
        result = await map_images.sync_images(client)
        assert result.downloaded == result.removed == 1
        assert not (storage / "kz_space (1).webp").exists()
        assert (storage / "kz_alpha.webp").read_bytes() == WEBP + b"updated"
        assert not list(storage.glob(".*.tmp"))


@pytest.mark.asyncio
async def test_failed_sync_keeps_old_image_manifest_and_deleted_files(
    storage: Path,
) -> None:
    files = {"kz_alpha": WEBP, "kz_old": WEBP}
    async with httpx.AsyncClient(transport=transport_for(files, [])) as client:
        await map_images.sync_images(client)
        old_manifest = (storage / "manifest.json").read_bytes()
        files["kz_alpha"] = b"not a webp"
        del files["kz_old"]
        with pytest.raises(ValueError, match="WebP"):
            await map_images.sync_images(client)
    assert (storage / "manifest.json").read_bytes() == old_manifest
    assert (storage / "kz_alpha.webp").read_bytes() == WEBP
    assert (storage / "kz_old.webp").exists()


@pytest.mark.parametrize(
    "payload",
    [
        {"truncated": True, "tree": []},
        {"truncated": False, "tree": []},
        {"tree": [{"type": "blob", "path": "webp/../escape.webp", "sha": "c" * 40}]},
        {"tree": [{"type": "blob", "path": "webp/kz_test.webp", "sha": "invalid"}]},
    ],
)
@pytest.mark.asyncio
async def test_invalid_manifest_rejected(
    storage: Path, payload: dict[str, object]
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if "/commits/" in request.url.path:
            return httpx.Response(
                200, json={"sha": COMMIT, "commit": {"tree": {"sha": TREE}}}
            )
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(ValueError):
            await map_images.sync_images(client)
    assert not (storage / "manifest.json").exists()


@pytest.mark.asyncio
async def test_blob_hash_mismatch(storage: Path) -> None:
    transport = transport_for({"kz_alpha": WEBP}, [])

    async def handle(request: httpx.Request) -> httpx.Response:
        if request.url.host == "raw.githubusercontent.com":
            return httpx.Response(200, content=WEBP + b"corrupt")
        return await transport.handle_async_request(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(ValueError, match="hash mismatch"):
            await map_images.sync_images(client)
    assert not (storage / "kz_alpha.webp").exists()


@pytest.mark.asyncio
async def test_http_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def handle(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503 if calls < 3 else 200)

    sleep = AsyncMock()
    monkeypatch.setattr(map_images.asyncio, "sleep", sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        assert (await map_images._get(client, "https://example.com")).status_code == 200
    assert calls == 3
    assert sleep.await_count == 2


@pytest.mark.parametrize(
    "name", ["../escape", "sub/name", "sub\\name", ".", "..", "\x00", " kz_test"]
)
@pytest.mark.usefixtures("storage")
def test_unsafe_path(name: str) -> None:
    assert map_images.image_path(name) is None


def test_symlink_and_invalid_manifest(storage: Path) -> None:
    target = storage / "outside"
    target.write_bytes(WEBP)
    (storage / "kz_link.webp").symlink_to(target)
    assert map_images.image_path("kz_link") is None
    (storage / "manifest.json").write_text("broken")
    assert map_images.read_manifest().files == {}


@pytest.mark.usefixtures("storage")
@pytest.mark.asyncio
async def test_schedule_and_failure_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    sync = AsyncMock(
        return_value=map_images.SyncResult(total=1, downloaded=0, removed=0)
    )
    monkeypatch.setattr(map_images, "sync_images", sync)
    now = datetime.now(UTC)
    manifest = map_images.ImageManifest(last_success_at=now)
    map_images._save_manifest(manifest)
    assert await map_images.sync_map_images() is None
    sync.assert_not_awaited()
    assert await map_images.sync_map_images(force=True) is not None
    manifest.last_success_at = now - timedelta(days=2)
    map_images._save_manifest(manifest)
    sync.side_effect = RuntimeError("offline")
    with pytest.raises(RuntimeError):
        await map_images.sync_map_images()
    assert map_images.read_manifest().retry_at > now
    sync.reset_mock()
    assert await map_images.sync_map_images() is None
    sync.assert_not_awaited()


@pytest.mark.usefixtures("storage")
@pytest.mark.asyncio
async def test_concurrent_workers_share_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    started = asyncio.Event()
    finish = asyncio.Event()

    async def sync(_: httpx.AsyncClient) -> map_images.SyncResult:
        started.set()
        await finish.wait()
        return map_images.SyncResult(total=1, downloaded=1, removed=0)

    monkeypatch.setattr(map_images, "sync_images", sync)
    first = asyncio.create_task(map_images.sync_map_images(force=True))
    try:
        await asyncio.wait_for(started.wait(), timeout=10)
        assert await map_images.sync_map_images(force=True) is None
    finally:
        finish.set()
        assert await first is not None


@pytest.mark.asyncio
async def test_endpoint_cache_head_and_validators(
    storage: Path, client: httpx.AsyncClient
) -> None:
    (storage / "kz_alpha.webp").write_bytes(WEBP)
    url = "/v1/maps/images/kz_alpha.webp"
    response = await client.get(url)
    assert response.content == WEBP
    assert response.headers["content-type"] == "image/webp"
    assert response.headers["cache-control"] == map_images.CACHE_CONTROL
    assert (await client.head(url)).content == b""
    for headers in (
        {"If-None-Match": response.headers["etag"]},
        {"If-None-Match": '"other", W/' + response.headers["etag"]},
        {"If-Modified-Since": response.headers["last-modified"]},
    ):
        cached = await client.get(url, headers=headers)
        assert cached.status_code == 304
        assert cached.headers["cache-control"] == map_images.CACHE_CONTROL
    assert (
        await client.get(url, headers={"If-Modified-Since": "bad"})
    ).status_code == 200
    assert (
        await client.get(
            url,
            headers={
                "If-None-Match": '"other"',
                "If-Modified-Since": response.headers["last-modified"],
            },
        )
    ).status_code == 200
    for path in ("missing", "sub%2Fname", "bad%5Cname", "bad%00name", "..%2Fescape"):
        missing = await client.get(f"/v1/maps/images/{path}.webp")
        assert missing.status_code == 404
        assert missing.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_http_retry_exhaustion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(map_images.asyncio, "sleep", AsyncMock())
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(503))
    ) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await map_images._get(client, "https://example.com")


@pytest.mark.asyncio
async def test_runner_sleeps_and_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    sync = AsyncMock(
        side_effect=[None, RuntimeError("offline"), asyncio.CancelledError()]
    )
    sleep = AsyncMock()
    monkeypatch.setattr(map_images, "sync_map_images", sync)
    monkeypatch.setattr(map_images.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await map_images.run_map_image_runner()
    assert [call.args[0] for call in sleep.await_args_list] == [60, 3600]
    task = asyncio.create_task(asyncio.Event().wait())
    await map_images.stop_map_image_runner(task)
    assert task.cancelled()
    await map_images.stop_map_image_runner(None)
