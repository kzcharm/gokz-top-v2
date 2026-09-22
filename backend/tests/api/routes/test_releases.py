from datetime import UTC, datetime, timedelta

import httpx
import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import GitHubRelease
from app.services import github_releases


def _release_payload(release_id: int = 1234) -> list[dict[str, object]]:
    return [
        {
            "id": release_id,
            "tag_name": "v1.2.3",
            "name": "Release 1.2.3",
            "html_url": "https://github.com/kzcharm/gokz-top-v2/releases/tag/v1.2.3",
            "published_at": "2026-09-22T10:00:00Z",
            "body": "## Features\n- feat: reactions",
        }
    ]


@pytest.mark.asyncio
async def test_releases_refresh_cache_and_serve_stale_on_github_failure(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fetch_success(*, limit: int) -> list[dict[str, object]]:
        assert limit == 20
        return _release_payload()

    monkeypatch.setattr(github_releases, "fetch_github_releases", fetch_success)
    response = await client.get(f"{settings.API_V1_STR}/releases")
    assert response.status_code == 200
    assert response.json()["data"][0]["id"] == 1234
    assert response.json()["data"][0]["reactions"] == {"groups": []}

    cached = await db.get(GitHubRelease, 1234)
    assert cached is not None
    cached.synced_at = datetime.now(UTC) - timedelta(hours=1)
    db.add(cached)
    await db.commit()

    async def fetch_failure(*, limit: int) -> list[dict[str, object]]:
        del limit
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(github_releases, "fetch_github_releases", fetch_failure)
    stale_response = await client.get(f"{settings.API_V1_STR}/releases")
    assert stale_response.status_code == 200
    assert stale_response.json()["data"][0]["tag_name"] == "v1.2.3"


@pytest.mark.asyncio
async def test_releases_return_502_without_cache(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fetch_failure(*, limit: int) -> list[dict[str, object]]:
        del limit
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(github_releases, "fetch_github_releases", fetch_failure)
    response = await client.get(f"{settings.API_V1_STR}/releases")
    assert response.status_code == 502
