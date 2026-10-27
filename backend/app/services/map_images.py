"""Persistent, incremental mirror of the public KZGlobalTeam WebP collection."""

import asyncio
import hashlib
import logging
import re
import time
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import httpx
import psycopg
from pydantic import BaseModel, Field, ValidationError

from app.core.config import settings

logger = logging.getLogger(__name__)
REPOSITORY = "KZGlobalTeam/map-images"
CACHE_CONTROL = "public, max-age=604800, s-maxage=604800"
LOCK_ID = int.from_bytes(
    hashlib.sha256(b"gokz-top-v2:map-images").digest()[:8], "big", signed=True
)
# Spaces and parentheses occur in map names; separators and control bytes do not.
MAP_NAME_PATTERN = re.compile(r"[^/\\\x00-\x1f\x7f]{1,255}\Z")


class ImageManifest(BaseModel):
    commit: str = ""
    files: dict[str, str] = Field(default_factory=dict)
    last_success_at: datetime | None = None
    retry_at: datetime | None = None


class SyncResult(BaseModel):
    total: int
    downloaded: int
    removed: int


def mirror_path(name: str) -> Path | None:
    """Validate upstream relative names, including medium/ and thumb/ variants."""
    parts = name.split("/")
    if any(
        not MAP_NAME_PATTERN.fullmatch(part) or part in {".", ".."} for part in parts
    ):
        return None
    root = settings.MAP_IMAGE_STORAGE_DIR.resolve()
    path = root.joinpath(*parts[:-1], f"{parts[-1]}.webp")
    # Reject symlinks in every component, including the final file.
    return path if path.resolve() == path else None


def image_path(map_name: str) -> Path | None:
    if "/" in map_name or map_name != map_name.strip():
        return None
    path = mirror_path(map_name)
    return path if path is not None and path.is_file() else None


def local_image_url(map_name: str) -> str | None:
    if image_path(map_name) is None:
        return None
    return (
        f"{settings.BACKEND_PUBLIC_URL.rstrip('/')}"
        f"{settings.API_V1_STR}/maps/images/{quote(map_name, safe='')}.webp"
    )


def read_manifest() -> ImageManifest:
    try:
        return ImageManifest.model_validate_json(
            (settings.MAP_IMAGE_STORAGE_DIR / "manifest.json").read_bytes()
        )
    except (OSError, ValidationError):
        return ImageManifest()


def _save_manifest(manifest: ImageManifest) -> None:
    root = settings.MAP_IMAGE_STORAGE_DIR
    root.mkdir(parents=True, exist_ok=True)
    temporary = root / ".manifest.tmp"
    try:
        temporary.write_text(manifest.model_dump_json(), encoding="utf-8")
        temporary.replace(root / "manifest.json")
    finally:
        temporary.unlink(missing_ok=True)


async def _get(client: httpx.AsyncClient, url: str) -> httpx.Response:
    for attempt in range(3):
        try:
            response = await client.get(url)
            response.raise_for_status()
            return response
        except (httpx.TransportError, httpx.HTTPStatusError):
            if attempt == 2:
                raise
            await asyncio.sleep(2**attempt)
    raise AssertionError("Unreachable")


async def sync_images(client: httpx.AsyncClient) -> SyncResult:
    """Caller holds the advisory lock; failed runs never publish a new manifest."""
    started = time.monotonic()
    root = settings.MAP_IMAGE_STORAGE_DIR
    root.mkdir(parents=True, exist_ok=True)
    previous = read_manifest()
    commit_data = (
        await _get(client, f"https://api.github.com/repos/{REPOSITORY}/commits/public")
    ).json()
    commit = commit_data["sha"]
    tree_sha = commit_data["commit"]["tree"]["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or not re.fullmatch(
        r"[0-9a-f]{40}", tree_sha
    ):
        raise ValueError("Invalid upstream commit")
    tree = (
        await _get(
            client,
            f"https://api.github.com/repos/{REPOSITORY}/git/trees/{tree_sha}?recursive=1",
        )
    ).json()
    if tree.get("truncated") or not isinstance(tree.get("tree"), list):
        raise ValueError("Incomplete upstream image tree")
    files: dict[str, str] = {}
    for entry in tree["tree"]:
        path = entry.get("path", "")
        if (
            entry.get("type") != "blob"
            or not path.startswith("webp/")
            or not path.endswith(".webp")
        ):
            continue
        name = path[len("webp/") : -len(".webp")]
        if mirror_path(name) is None:
            raise ValueError("Unsafe upstream image filename")
        sha = entry["sha"]
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ValueError("Invalid upstream blob hash")
        files[name] = sha
    if not files:
        raise ValueError("Refusing to replace the mirror with an empty collection")

    semaphore = asyncio.Semaphore(8)

    async def download(name: str, sha: str) -> bool:
        path = mirror_path(name)
        if path is None:
            raise ValueError("Unsafe image path")
        if previous.files.get(name) == sha and path.is_file():
            return False
        async with semaphore:
            url = f"https://raw.githubusercontent.com/{REPOSITORY}/{commit}/webp/{quote(name, safe='')}.webp"
            content = (await _get(client, url)).content
            blob = b"blob " + str(len(content)).encode() + b"\0" + content
            if hashlib.sha1(blob, usedforsecurity=False).hexdigest() != sha:
                raise ValueError("Map image blob hash mismatch")
            if len(content) < 12 or content[:4] != b"RIFF" or content[8:12] != b"WEBP":
                raise ValueError("Invalid WebP image")
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f".{path.name}.tmp")
            try:
                temporary.write_bytes(content)
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
            return True

    # Finish all outstanding downloads before releasing the shared lock on failure.
    results = await asyncio.gather(
        *(download(name, sha) for name, sha in files.items()), return_exceptions=True
    )
    for download_result in results:
        if isinstance(download_result, BaseException):
            raise download_result
    removed = 0
    for name in previous.files.keys() - files.keys():
        path = mirror_path(name)
        if path is not None and path.is_file():
            path.unlink()
            removed += 1
    _save_manifest(
        ImageManifest(commit=commit, files=files, last_success_at=datetime.now(UTC))
    )
    result = SyncResult(
        total=len(files),
        downloaded=sum(value is True for value in results),
        removed=removed,
    )
    logger.info(
        "Map image sync complete: %s (%.1fs)",
        result.model_dump(),
        time.monotonic() - started,
    )
    return result


async def sync_map_images(*, force: bool = False) -> SyncResult | None:
    uri = str(settings.SQLALCHEMY_DATABASE_URI).replace(
        "postgresql+psycopg", "postgresql", 1
    )
    async with await psycopg.AsyncConnection.connect(
        uri, autocommit=True
    ) as connection:
        async with connection.cursor() as cursor:
            await cursor.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_ID,))
            row = await cursor.fetchone()
        if not row or not row[0]:
            return None
        # Read only after acquiring the lock: another worker may have just synced.
        manifest = read_manifest()
        now = datetime.now(UTC)
        if not force and (
            (manifest.retry_at is not None and manifest.retry_at > now)
            or (
                manifest.last_success_at is not None
                and manifest.retry_at is None
                and manifest.last_success_at
                + timedelta(seconds=settings.MAP_IMAGE_SYNC_INTERVAL_SECONDS)
                > now
            )
        ):
            return None
        try:
            async with httpx.AsyncClient(
                timeout=30,
                follow_redirects=True,
                headers={"User-Agent": "gokz-top-map-images"},
            ) as client:
                return await sync_images(client)
        except Exception:
            manifest.retry_at = datetime.now(UTC) + timedelta(hours=1)
            _save_manifest(manifest)
            logger.exception(
                "Map image sync failed; existing images retained; retry in one hour"
            )
            raise


async def run_map_image_runner() -> None:
    while True:
        try:
            await sync_map_images()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Map image runner could not complete synchronization")
            await asyncio.sleep(3600)
        else:
            await asyncio.sleep(60)


async def stop_map_image_runner(task: asyncio.Task[None] | None) -> None:
    if task is not None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
