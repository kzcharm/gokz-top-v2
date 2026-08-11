import hashlib
import hmac

import pytest
from httpx import AsyncClient

from app.api.v1 import youtube_webhooks
from app.core.config import settings


@pytest.mark.asyncio
async def test_youtube_websub_challenge_accepts_a_valid_channel_topic(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "YOUTUBE_WEBSUB_ENABLED", True)
    monkeypatch.setattr(settings, "YOUTUBE_WEBSUB_SECRET", "websub-secret")

    response = await client.get(
        "/v1/webhooks/youtube",
        params={
            "hub.mode": "subscribe",
            "hub.topic": (
                "https://www.youtube.com/xml/feeds/videos.xml?"
                "channel_id=UC12345678901234567890AB"
            ),
            "hub.challenge": "challenge-value",
        },
    )

    assert response.status_code == 200
    assert response.text == "challenge-value"


@pytest.mark.asyncio
async def test_youtube_websub_challenge_rejects_untrusted_topic(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "YOUTUBE_WEBSUB_ENABLED", True)
    monkeypatch.setattr(settings, "YOUTUBE_WEBSUB_SECRET", "websub-secret")

    response = await client.get(
        "/v1/webhooks/youtube",
        params={
            "hub.mode": "subscribe",
            "hub.topic": "https://example.com/feed",
            "hub.challenge": "challenge-value",
        },
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_youtube_websub_notification_requires_a_valid_signature(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "YOUTUBE_WEBSUB_ENABLED", True)
    monkeypatch.setattr(settings, "YOUTUBE_WEBSUB_SECRET", "websub-secret")

    response = await client.post("/v1/webhooks/youtube", content=b"notification")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_youtube_websub_notification_schedules_media_sync(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = b"notification"
    secret = "websub-secret"
    signature = hmac.new(secret.encode(), body, hashlib.sha1).hexdigest()
    scheduled = False

    def _schedule() -> None:
        nonlocal scheduled
        scheduled = True

    monkeypatch.setattr(settings, "YOUTUBE_WEBSUB_ENABLED", True)
    monkeypatch.setattr(settings, "YOUTUBE_WEBSUB_SECRET", secret)
    monkeypatch.setattr(youtube_webhooks, "schedule_youtube_media_sync", _schedule)

    response = await client.post(
        "/v1/webhooks/youtube",
        content=body,
        headers={"X-Hub-Signature": f"sha1={signature}"},
    )

    assert response.status_code == 204
    assert scheduled
