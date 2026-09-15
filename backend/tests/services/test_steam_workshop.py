from datetime import timedelta

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import WorkshopPreviewUrlCache
from app.models.utils import get_datetime_utc
from app.services import steam_workshop

pytestmark = pytest.mark.asyncio


async def test_get_cached_workshop_preview_urls_batches_refreshes(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = get_datetime_utc()
    db.add(
        WorkshopPreviewUrlCache(
            workshop_id=111,
            preview_url="https://steam.example/cached.jpg",
            fetched_at=now,
            last_attempted_at=now,
        )
    )
    db.add(
        WorkshopPreviewUrlCache(
            workshop_id=222,
            preview_url="https://steam.example/stale.jpg",
            fetched_at=now - timedelta(days=2),
            last_attempted_at=now - timedelta(days=2),
        )
    )
    await db.commit()
    requested_batches: list[list[str]] = []

    async def _fake_fetch_workshop_file_details(
        *,
        workshop_ids: list[str],
        client: object | None = None,
    ) -> dict[str, steam_workshop.SteamWorkshopFileDetails]:
        assert client is None
        requested_batches.append(workshop_ids)
        return {
            "222": steam_workshop.SteamWorkshopFileDetails(
                publishedfileid="222",
                creator=None,
                preview_url="https://steam.example/refreshed.jpg",
            ),
            "333": steam_workshop.SteamWorkshopFileDetails(
                publishedfileid="333",
                creator=None,
                preview_url=None,
            ),
        }

    monkeypatch.setattr(
        steam_workshop,
        "fetch_workshop_file_details",
        _fake_fetch_workshop_file_details,
    )

    result = await steam_workshop.get_cached_workshop_preview_urls(
        session=db,
        workshop_ids=["111", "222", "333", "222", "invalid"],
    )

    assert requested_batches == [["222", "333"]]
    assert result == {
        "111": "https://steam.example/cached.jpg",
        "222": "https://steam.example/refreshed.jpg",
        "333": None,
    }
    refreshed_row = await db.get(WorkshopPreviewUrlCache, 222)
    missing_row = await db.get(WorkshopPreviewUrlCache, 333)
    assert refreshed_row is not None
    assert refreshed_row.preview_url == "https://steam.example/refreshed.jpg"
    assert missing_row is not None
    assert missing_row.preview_url is None
    assert missing_row.error_message == "Workshop preview not found"
