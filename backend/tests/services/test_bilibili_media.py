from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import MediaPost, Player, PlayerSocialLink, PlayerSocialPlatform
from app.services import bilibili_media
from tests.utils.utils import random_steamid64


@pytest.fixture(autouse=True)
def _reset_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bilibili_media, "_request_backoffs", {})


class _Response:
    def __init__(self, payload: dict[str, Any], *, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code
        self.headers: dict[str, str] = {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict[str, Any]:
        return self.payload


def test_is_allowed_bilibili_thumbnail_url_rejects_untrusted_hosts() -> None:
    assert bilibili_media.is_allowed_bilibili_thumbnail_url(
        "https://i0.hdslb.com/bfs/archive/thumbnail.jpg"
    )
    assert bilibili_media.is_allowed_bilibili_thumbnail_url(
        "http://i1.hdslb.com/bfs/archive/thumbnail.jpg"
    )
    assert not bilibili_media.is_allowed_bilibili_thumbnail_url(
        "https://hdslb.com.attacker.example/thumbnail.jpg"
    )
    assert not bilibili_media.is_allowed_bilibili_thumbnail_url(
        "https://example.com/thumbnail.jpg"
    )


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


def test_parse_view_count_normalizes_bilibili_upload_values() -> None:
    assert bilibili_media._parse_view_count(42) == 42
    assert bilibili_media._parse_view_count("17") == 17
    assert bilibili_media._parse_view_count(-1) == 0
    assert bilibili_media._parse_view_count("invalid") == 0


@pytest.mark.asyncio
async def test_fetch_bilibili_posts_backs_off_before_retrying_anti_bot_response(
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

    now = datetime.now(UTC)
    monkeypatch.setattr(bilibili_media, "get_datetime_utc", lambda: now)
    with pytest.raises(bilibili_media.BilibiliBackoffError):
        await bilibili_media.fetch_bilibili_posts(123, page_size=30)
    with pytest.raises(bilibili_media.BilibiliBackoffError):
        await bilibili_media.fetch_bilibili_posts(123, page_size=30)
    assert upload_attempts == 1
    now += timedelta(minutes=15)
    posts = await bilibili_media.fetch_bilibili_posts(123, page_size=30)

    assert posts == [{"bvid": "BV1test", "created": 1_700_000_000}]
    assert headers is not None
    assert headers["Cookie"] == "SESSDATA=service-cookie"
    assert [url for url, _ in calls] == [
        bilibili_media.BILIBILI_WBI_KEYS_URL,
        bilibili_media.BILIBILI_UPLOADS_URL,
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

    upload_title = "Recent KZ run"
    upload_views = 42

    async def _fetch_posts(_: int, *, cutoff: datetime) -> list[dict[str, Any]]:
        assert cutoff <= bilibili_media.get_datetime_utc()
        return [
            {
                "bvid": "BV1media",
                "created": 1_786_032_000,
                "title": upload_title,
                "description": "A precise run",
                "pic": "https://example.com/thumb.jpg",
                "length": "1:42",
                "play": upload_views,
            }
        ]

    async def _cache_thumbnail(*, bvid: str, raw_url: object) -> str | None:
        assert bvid == "BV1media"
        assert raw_url == "https://example.com/thumb.jpg"
        return str(raw_url)

    detail_calls: list[str] = []

    async def _fetch_detail(bvid: str) -> dict[str, Any]:
        detail_calls.append(bvid)
        return {
            "title": upload_title,
            "desc": "A precise run",
            "pic": "https://example.com/thumb.jpg",
            "duration": 102,
            "stat": {"view": 42},
        }

    monkeypatch.setattr(bilibili_media, "fetch_bilibili_posts", _fetch_posts)
    monkeypatch.setattr(bilibili_media, "fetch_bilibili_video_detail", _fetch_detail)
    monkeypatch.setattr(bilibili_media, "cache_bilibili_thumbnail", _cache_thumbnail)

    assert await bilibili_media.sync_bilibili_media_once(session=db) == 1

    post = (await db.exec(select(MediaPost))).one()
    assert post.platform == PlayerSocialPlatform.BILIBILI
    assert post.external_video_id == "BV1media"
    assert post.url == "https://www.bilibili.com/video/BV1media"
    assert post.duration_seconds == 102
    assert post.view_count == 42
    assert post.tags is None
    assert post.is_kz_video is True

    async def _unexpected_thumbnail(**_: object) -> str:
        pytest.fail("Unchanged videos must reuse their cached thumbnail")

    monkeypatch.setattr(
        bilibili_media, "cache_bilibili_thumbnail", _unexpected_thumbnail
    )
    upload_views = 43
    metadata_checked_at = post.metadata_checked_at
    # View-count failures must not invalidate successful canonical metadata.
    post.last_error = "View-count refresh failed"
    await db.commit()
    await bilibili_media.sync_bilibili_media_once(session=db)
    await db.refresh(post)
    assert detail_calls == ["BV1media"]
    assert post.view_count == 43
    assert post.metadata_checked_at == metadata_checked_at

    now = datetime.now(UTC) + timedelta(hours=25)
    # A view refresh must not postpone the independent metadata refresh.
    post.last_checked_at = now
    await db.commit()
    monkeypatch.setattr(bilibili_media, "get_datetime_utc", lambda: now)
    await bilibili_media.sync_bilibili_media_once(session=db)
    assert detail_calls == ["BV1media", "BV1media"]
    upload_title = "Updated KZ run"
    await bilibili_media.sync_bilibili_media_once(session=db)
    await db.refresh(post)
    assert detail_calls == ["BV1media"] * 3
    assert post.title == "Updated KZ run"


@pytest.mark.asyncio
async def test_sync_bilibili_media_retries_failed_tags_and_promotes_hidden_post(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = Player(steamid64=random_steamid64(), name="Tag Player")
    db.add(player)
    await db.commit()
    link = PlayerSocialLink(
        player_steamid64=player.steamid64,
        platform=PlayerSocialPlatform.BILIBILI,
        account_identifier="654321",
        verified=True,
    )
    db.add(link)
    await db.commit()

    async def _fetch_posts(_: int, *, cutoff: datetime) -> list[dict[str, Any]]:
        assert cutoff < datetime.now(UTC)
        return [{"bvid": "BVtag", "created": 1_786_032_000}]

    async def _fetch_detail(_: str) -> dict[str, Any]:
        return {
            "title": "A new upload",
            "desc": "No text match",
            "pic": "https://example.com/thumb.jpg",
            "duration": 42,
            "stat": {"view": 5},
        }

    tag_attempts = 0

    async def _fetch_tags(_: str) -> list[str]:
        nonlocal tag_attempts
        tag_attempts += 1
        if tag_attempts == 1:
            raise RuntimeError("temporary tag failure")
        return ["KZ"]

    cached: list[str] = []

    async def _cache(*, bvid: str, raw_url: object) -> str | None:
        cached.append(bvid)
        return str(raw_url)

    monkeypatch.setattr(bilibili_media, "fetch_bilibili_posts", _fetch_posts)
    monkeypatch.setattr(bilibili_media, "fetch_bilibili_video_detail", _fetch_detail)
    monkeypatch.setattr(bilibili_media, "fetch_bilibili_video_tags", _fetch_tags)
    monkeypatch.setattr(bilibili_media, "cache_bilibili_thumbnail", _cache)

    await bilibili_media.sync_bilibili_media_once(session=db)
    post = (await db.exec(select(MediaPost))).one()
    assert post.tags is None
    assert post.is_kz_video is False
    assert post.thumbnail_url is None
    assert cached == []

    await bilibili_media.sync_bilibili_media_once(session=db)
    await db.refresh(post)
    assert post.tags == ["KZ"]
    assert post.is_kz_video is True
    assert post.thumbnail_url == "https://example.com/thumb.jpg"
    assert cached == ["BVtag"]


@pytest.mark.asyncio
async def test_sync_bilibili_keeps_title_matches_visible_when_details_are_blocked(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = Player(steamid64=random_steamid64(), name="Blocked metadata")
    db.add(player)
    await db.flush()
    link = PlayerSocialLink(
        player_steamid64=player.steamid64,
        platform=PlayerSocialPlatform.BILIBILI,
        account_identifier="7654321",
        verified=True,
    )
    db.add(link)
    await db.commit()

    async def _posts(_: int, *, cutoff: datetime) -> list[dict[str, Any]]:
        assert cutoff < datetime.now(UTC)
        return [
            {
                "bvid": bvid,
                "title": title,
                "created": int(datetime.now(UTC).timestamp()),
                "length": "1:42",
            }
            for bvid, title in [
                ("BVblocked", "【GOKZ】New run"),
                ("BVsecond", "KZ run"),
                ("BVhidden", "Cooking"),
            ]
        ]

    detail_requests = 0

    def _response(request: httpx.Request) -> httpx.Response:
        nonlocal detail_requests
        detail_requests += 1
        return httpx.Response(412, text="Blocked HTML response", request=request)

    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        bilibili_media.httpx,
        "AsyncClient",
        lambda **kw: client_type(**kw, transport=httpx.MockTransport(_response)),
    )
    monkeypatch.setattr(bilibili_media, "fetch_bilibili_posts", _posts)
    for _ in range(2):
        await bilibili_media.sync_bilibili_media_once(session=db)
    posts = (
        await db.exec(select(MediaPost).order_by(MediaPost.external_video_id))
    ).all()
    assert len(posts) == 3
    assert {p.external_video_id for p in posts if p.is_kz_video} == {
        "BVblocked",
        "BVsecond",
    }
    assert all(p.last_error is not None for p in posts)
    assert all(p.metadata_checked_at is None for p in posts)
    assert all(p.duration_seconds == 102 for p in posts)
    assert detail_requests == 1  # Shared cooldown prevents a request per video/cycle.


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,payload", [(412, {}), (429, {}), (200, {"code": -412})]
)
async def test_detail_requests_back_off_without_retries_and_recover(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    payload: dict[str, Any],
) -> None:
    now = datetime(2026, 10, 30, tzinfo=UTC)
    calls = 0
    blocked = True

    def _response(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if blocked:
            return httpx.Response(status, json=payload, request=request)
        return httpx.Response(
            200, json={"code": 0, "data": {"title": "KZ run"}}, request=request
        )

    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        bilibili_media.httpx,
        "AsyncClient",
        lambda **kw: client_type(**kw, transport=httpx.MockTransport(_response)),
    )
    monkeypatch.setattr(bilibili_media, "get_datetime_utc", lambda: now)
    monkeypatch.setattr(bilibili_media, "_request_backoffs", {})
    for _ in range(2):
        with pytest.raises(bilibili_media.BilibiliBackoffError):
            await bilibili_media.fetch_bilibili_video_detail("BVtest")
    assert calls == 1
    now += timedelta(minutes=15)
    with pytest.raises(bilibili_media.BilibiliBackoffError):
        await bilibili_media.fetch_bilibili_video_detail("BVtest")
    assert calls == 2
    now += timedelta(minutes=15)
    with pytest.raises(bilibili_media.BilibiliBackoffError):
        await bilibili_media.fetch_bilibili_video_detail("BVtest")
    assert calls == 2  # Second rejection doubles the cooldown to 30 minutes.
    now += timedelta(minutes=15)
    blocked = False
    assert await bilibili_media.fetch_bilibili_video_detail("BVtest") == {
        "title": "KZ run"
    }
    assert calls == 3
    assert not bilibili_media._request_backoffs


@pytest.mark.asyncio
@pytest.mark.parametrize("retry_after", ["7200", "Fri, 30 Oct 2026 02:00:00 GMT"])
async def test_backoff_respects_retry_after_and_is_shared_with_view_refresh(
    monkeypatch: pytest.MonkeyPatch,
    retry_after: str,
) -> None:
    now = datetime(2026, 10, 30, tzinfo=UTC)
    calls = 0

    def _response(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            412,
            text="blocked HTML response",
            headers={"Retry-After": retry_after},
            request=request,
        )

    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        bilibili_media.httpx,
        "AsyncClient",
        lambda **kw: client_type(**kw, transport=httpx.MockTransport(_response)),
    )
    monkeypatch.setattr(bilibili_media, "get_datetime_utc", lambda: now)
    with pytest.raises(bilibili_media.BilibiliBackoffError):
        await bilibili_media.fetch_bilibili_video_detail("BVtest")
    now += timedelta(minutes=60)
    with pytest.raises(bilibili_media.BilibiliBackoffError):
        await bilibili_media.fetch_bilibili_video_view_counts(["BVother"])
    assert calls == 1
    assert bilibili_media._request_backoffs[
        bilibili_media.BILIBILI_VIDEO_VIEW_URL
    ].retry_at == datetime(2026, 10, 30, 2, tzinfo=UTC)
