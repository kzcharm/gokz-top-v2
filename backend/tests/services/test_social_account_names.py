from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.models import Player, PlayerSocialPlatform
from app.services import social_account_names as names
from tests.utils.utils import random_steamid64


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("platform", "identifier", "payload", "expected"),
    [
        ("bilibili", "123456", {"code": 0, "data": {"card": {"name": "从雨"}}}, "从雨"),
        (
            "youtube",
            "channel/UC123",
            {"items": [{"snippet": {"title": "Creator"}}]},
            "Creator",
        ),
        ("twitch", "streamer", {"data": [{"display_name": "Streamer"}]}, "Streamer"),
        ("bilibili", "123456", {"code": -403}, None),
        ("youtube", "@missing", {"items": []}, None),
    ],
)
async def test_fetch_platform_name(
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    identifier: str,
    payload: dict[str, object],
    expected: str | None,
) -> None:
    from app.services import live_streams

    monkeypatch.setattr(settings, "YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr(settings, "TWITCH_CLIENT_ID", "test-client")
    monkeypatch.setattr(settings, "TWITCH_CLIENT_SECRET", "test-secret")

    async def token() -> str:
        return "test-token"

    monkeypatch.setattr(live_streams, "_get_twitch_app_access_token", token)
    client_class = httpx.AsyncClient
    monkeypatch.setattr(
        names.httpx,
        "AsyncClient",
        lambda **kwargs: client_class(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
            **kwargs,
        ),
    )
    try:
        result = await names.fetch_social_account_name(
            platform=PlayerSocialPlatform(platform), account_identifier=identifier
        )
    except (KeyError, IndexError):
        result = None
    assert result == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "initial_metadata", [None, {"bilibili_verification": {"keep": True}}]
)
async def test_cache_persists_names_preserves_metadata_and_invalidates_changed_account(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    initial_metadata: dict[str, object] | None,
) -> None:
    player = Player(steamid64=random_steamid64(), name="Test Player")
    db.add(player)
    await db.commit()
    link = await crud.create_player_social_link(
        session=db,
        player_steamid64=player.steamid64,
        url="https://space.bilibili.com/123456",
        metadata_json=initial_metadata,
    )
    calls = []

    async def fetch(**kwargs: object) -> str:
        calls.append(kwargs)
        return "从雨"

    monkeypatch.setattr(names, "fetch_social_account_name", fetch)
    await names.refresh_social_account_names(session=db, links=[link])
    await db.refresh(link)
    assert link.metadata_json is not None
    if initial_metadata:
        assert link.metadata_json["bilibili_verification"] == {"keep": True}
    assert crud.to_admin_player_social_link_public(link=link).account_name == "从雨"
    await names.refresh_social_account_names(session=db, links=[link])
    assert len(calls) == 1

    await crud.update_player_social_link(
        session=db, link=link, url="https://space.bilibili.com/654321"
    )
    assert crud.to_admin_player_social_link_public(link=link).account_name is None


@pytest.mark.asyncio
@pytest.mark.parametrize("previous_name", [None, "Cached Name"])
async def test_failed_refresh_keeps_name_and_throttles_retries(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, previous_name: str | None
) -> None:
    player = Player(steamid64=random_steamid64(), name="Test Player")
    db.add(player)
    await db.commit()
    link = await crud.create_player_social_link(
        session=db,
        player_steamid64=player.steamid64,
        url="https://www.youtube.com/@creator",
        metadata_json={
            "account_name_cache": names.SocialAccountNameCache(
                account_identifier="@creator",
                name=previous_name,
                checked_at=datetime.now(UTC) - timedelta(days=2),
            ).model_dump(mode="json")
        },
    )
    calls = []

    async def fail(**kwargs: object) -> str:
        calls.append(kwargs)
        raise httpx.ConnectError("unavailable")

    monkeypatch.setattr(names, "fetch_social_account_name", fail)
    await names.refresh_social_account_names(session=db, links=[link])
    await names.refresh_social_account_names(session=db, links=[link])
    assert len(calls) == 1
    assert (
        crud.to_admin_player_social_link_public(link=link).account_name == previous_name
    )
