from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import MediaPost, Player, PlayerSocialLink, PlayerSocialPlatform
from app.services import bilibili_media
from tests.utils.utils import random_steamid64


class _Response:
    def __init__(self, payload: dict[str, Any], *, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict[str, Any]:
        return self.payload


def test_sign_wbi_params_sanitizes_values_and_adds_stable_signature() -> None:
    params = bilibili_media._sign_wbi_params(
        {"keyword": "KZ!('*)", "mid": 123},
        img_key="abcdefghijklmnopqrstuvwxyz01234567",
        sub_key="ABCDEFGHIJKLMNOPQRSTUVWXYZ76543210",
        wts=1_700_000_000,
    )

    assert params == {
        "keyword": "KZ",
        "mid": "123",
        "wts": "1700000000",
        "w_rid": "6ac974dfd14ea016abac2a82f22fa0e6",
    }


@pytest.mark.asyncio
async def test_fetch_bilibili_posts_retries_anti_bot_response_with_fresh_wbi_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object] | None]] = []
    headers: dict[str, str] | None = None
    upload_attempts = 0

    class _Client:
        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def get(
            self, url: str, *, params: dict[str, object] | None = None
        ) -> _Response:
            nonlocal upload_attempts
            calls.append((url, params))
            if url == bilibili_media.BILIBILI_WBI_KEYS_URL:
                return _Response(
                    {
                        "code": 0,
                        "data": {
                            "wbi_img": {
                                "img_url": "https://i0.hdslb.com/a/abcdefghijklmnopqrstuvwxyz01234567.png",
                                "sub_url": "https://i0.hdslb.com/b/ABCDEFGHIJKLMNOPQRSTUVWXYZ76543210.png",
                            }
                        },
                    }
                )
            upload_attempts += 1
            if upload_attempts == 1:
                return _Response({"code": -412, "message": "anti-bot"}, status_code=412)
            return _Response(
                {
                    "code": 0,
                    "data": {
                        "list": {
                            "vlist": [
                                {
                                    "bvid": "BV1test",
                                    "created": 1_700_000_000,
                                }
                            ]
                        },
                        "page": {"count": 1},
                    },
                }
            )

    def _client_factory(**kwargs: object) -> _Client:
        nonlocal headers
        headers = kwargs.get("headers")  # type: ignore[assignment]
        return _Client()

    monkeypatch.setattr(settings, "BILIBILI_COOKIE", "SESSDATA=service-cookie")
    monkeypatch.setattr(bilibili_media, "_wbi_keys", None)
    monkeypatch.setattr(bilibili_media, "_wbi_keys_fetched_at", None)
    monkeypatch.setattr(bilibili_media.httpx, "AsyncClient", _client_factory)

    posts = await bilibili_media.fetch_bilibili_posts(123, page_size=30)

    assert posts == [{"bvid": "BV1test", "created": 1_700_000_000}]
    assert headers is not None
    assert headers["Cookie"] == "SESSDATA=service-cookie"
    assert [url for url, _ in calls] == [
        bilibili_media.BILIBILI_WBI_KEYS_URL,
        bilibili_media.BILIBILI_UPLOADS_URL,
        bilibili_media.BILIBILI_WBI_KEYS_URL,
        bilibili_media.BILIBILI_UPLOADS_URL,
    ]


@pytest.mark.asyncio
async def test_fetch_bilibili_posts_stops_after_reaching_retention_cutoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cutoff = datetime(2026, 8, 1, tzinfo=UTC)
    page_numbers: list[str] = []

    class _Client:
        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def get(
            self, url: str, *, params: dict[str, str] | None = None
        ) -> _Response:
            if url == bilibili_media.BILIBILI_WBI_KEYS_URL:
                return _Response(
                    {
                        "code": 0,
                        "data": {
                            "wbi_img": {
                                "img_url": "https://i0.hdslb.com/a/abcdefghijklmnopqrstuvwxyz01234567.png",
                                "sub_url": "https://i0.hdslb.com/b/ABCDEFGHIJKLMNOPQRSTUVWXYZ76543210.png",
                            }
                        },
                    }
                )
            assert params is not None
            page_numbers.append(params["pn"])
            return _Response(
                {
                    "code": 0,
                    "data": {
                        "list": {
                            "vlist": [
                                {
                                    "bvid": "BV1old",
                                    "created": int(
                                        (cutoff - timedelta(seconds=1)).timestamp()
                                    ),
                                }
                            ]
                        },
                        "page": {"count": 100},
                    },
                }
            )

    monkeypatch.setattr(bilibili_media, "_wbi_keys", None)
    monkeypatch.setattr(bilibili_media, "_wbi_keys_fetched_at", None)
    monkeypatch.setattr(bilibili_media.httpx, "AsyncClient", lambda **_: _Client())

    posts = await bilibili_media.fetch_bilibili_posts(123, cutoff=cutoff)

    assert posts == [
        {"bvid": "BV1old", "created": int((cutoff - timedelta(seconds=1)).timestamp())}
    ]
    assert page_numbers == ["1"]


@pytest.mark.asyncio
async def test_sync_bilibili_media_creates_posts_for_verified_links(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = Player(steamid64=random_steamid64(), name="Bilibili Player")
    db.add(player)
    await db.commit()
    link = PlayerSocialLink(
        player_steamid64=player.steamid64,
        platform=PlayerSocialPlatform.BILIBILI,
        account_identifier="123456",
        verified=True,
    )
    db.add(link)
    await db.commit()

    async def _fetch_posts(_: int, *, cutoff: datetime) -> list[dict[str, Any]]:
        assert cutoff < datetime.now(UTC)
        return [
            {
                "bvid": "BV1media",
                "created": 1_786_032_000,
                "title": "Recent KZ run",
                "description": "A precise run",
                "pic": "https://example.com/thumb.jpg",
                "length": "1:42",
            }
        ]

    async def _cache_thumbnail(*, bvid: str, raw_url: object) -> str | None:
        assert bvid == "BV1media"
        assert raw_url == "https://example.com/thumb.jpg"
        return str(raw_url)

    monkeypatch.setattr(bilibili_media, "fetch_bilibili_posts", _fetch_posts)
    monkeypatch.setattr(bilibili_media, "cache_bilibili_thumbnail", _cache_thumbnail)

    assert await bilibili_media.sync_bilibili_media_once(session=db) == 1

    post = (await db.exec(select(MediaPost))).one()
    assert post.platform == PlayerSocialPlatform.BILIBILI
    assert post.external_video_id == "BV1media"
    assert post.url == "https://www.bilibili.com/video/BV1media"
    assert post.duration_seconds == 102
