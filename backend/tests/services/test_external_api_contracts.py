"""Validate upstream payloads without depending on live API credentials."""

from unittest.mock import AsyncMock

import httpx
import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Map, PlayerSocialLink, PlayerSocialPlatform
from app.services import bilibili_media as bilibili
from app.services import live_streams, steam_workshop, vanilla_tier
from app.services import video_platform_followers as followers
from app.services import youtube_media as youtube


@pytest.fixture
def mock_api(monkeypatch: pytest.MonkeyPatch):
    original = httpx.AsyncClient
    responses = []
    requests = []

    def handler(request):
        requests.append(request)
        response = responses.pop(0)
        return (
            response
            if isinstance(response, httpx.Response)
            else httpx.Response(200, json=response)
        )

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: original(transport=transport, **kwargs)
    )
    monkeypatch.setattr(followers.settings, "YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr(followers.settings, "TWITCH_CLIENT_ID", "test-client")
    monkeypatch.setattr(followers.settings, "TWITCH_CLIENT_SECRET", "test-secret")
    return responses, requests


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "platform,payload,count",
    [
        (PlayerSocialPlatform.BILIBILI, {"code": 0, "data": {"follower": " 21 "}}, 21),
        (
            PlayerSocialPlatform.YOUTUBE,
            {"items": [{"statistics": {"subscriberCount": "32"}}]},
            32,
        ),
        (PlayerSocialPlatform.TWITCH, {"total": 43}, 43),
    ],
)
async def test_video_followers_normalize_upstream_counts(
    mock_api, monkeypatch: pytest.MonkeyPatch, platform, payload, count
) -> None:
    responses, requests = mock_api
    if platform == PlayerSocialPlatform.TWITCH:
        monkeypatch.setattr(
            live_streams,
            "_get_twitch_app_access_token",
            AsyncMock(return_value="test-access"),
        )
        responses.append({"data": [{"id": "123"}]})
    responses.append(payload)
    link = PlayerSocialLink(
        player_steamid64=1,
        platform=platform,
        account_identifier="@channel"
        if platform == PlayerSocialPlatform.YOUTUBE
        else "123",
    )
    assert await followers.fetch_video_platform_follower_count(link=link) == count
    assert requests


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "platform,payload",
    [
        ("bilibili", {"code": -1, "message": "denied"}),
        ("bilibili", {"code": 0, "data": []}),
        ("youtube", {"items": []}),
        ("youtube", {"items": [None]}),
        ("youtube", {"items": [{"statistics": None}]}),
        ("youtube", {"items": [{"statistics": {"hiddenSubscriberCount": True}}]}),
        ("youtube", {"items": [{"statistics": {"subscriberCount": -1}}]}),
        ("twitch", {"data": []}),
        ("twitch", {"data": [{"id": None}]}),
    ],
)
async def test_follower_apis_reject_malformed_or_private_counts(
    mock_api, monkeypatch: pytest.MonkeyPatch, platform, payload
) -> None:
    responses, _ = mock_api
    responses.append(payload)
    monkeypatch.setattr(
        live_streams,
        "_get_twitch_app_access_token",
        AsyncMock(return_value="test-access"),
    )
    method = getattr(followers, f"fetch_{platform}_follower_count")
    with pytest.raises(ValueError):
        await method(account_identifier="@channel" if platform == "youtube" else "123")


@pytest.mark.parametrize("value", [True, False, -1, "-1", "invalid", None])
def test_negative_or_non_numeric_follower_counts_are_rejected(value) -> None:
    with pytest.raises(ValueError):
        followers._parse_non_negative_int(value)


def test_youtube_account_forms_and_safe_error_messages() -> None:
    assert followers._youtube_channel_params("channel/UC123") == {"id": "UC123"}
    assert followers._youtube_channel_params("user/test") == {"forUsername": "test"}
    assert followers._youtube_channel_params("@test") == {"forHandle": "@test"}
    with pytest.raises(ValueError):
        followers._youtube_channel_params("arbitrary/path")
    assert followers._truncate_error_message(ValueError()) == "ValueError"
    assert len(followers._truncate_error_message(ValueError("x" * 700))) == 500


@pytest.mark.asyncio
async def test_unconfigured_follower_credentials_fail_before_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(followers.settings, "YOUTUBE_API_KEY", None)
    monkeypatch.setattr(followers.settings, "TWITCH_CLIENT_SECRET", None)
    with pytest.raises(RuntimeError, match="credentials"):
        await followers.fetch_youtube_follower_count(account_identifier="@channel")
    with pytest.raises(RuntimeError, match="credentials"):
        await followers.fetch_twitch_follower_count(account_identifier="test")
    with pytest.raises(ValueError, match="Unsupported"):
        await followers.fetch_video_platform_follower_count(
            link=PlayerSocialLink(
                player_steamid64=1,
                platform=PlayerSocialPlatform.DISCORD,
                account_identifier="123",
            )
        )


@pytest.mark.asyncio
async def test_workshop_details_validate_urls_and_skip_malformed_rows(mock_api) -> None:
    responses, requests = mock_api
    responses.append(
        {
            "response": {
                "publishedfiledetails": [
                    None,
                    {"publishedfileid": "bad"},
                    {
                        "publishedfileid": "123",
                        "creator": " 76561199022242128 ",
                        "preview_url": " https://cdn.example/preview.jpg ",
                    },
                    {"publishedfileid": "456", "preview_url": "javascript:bad"},
                ]
            }
        }
    )
    details = await steam_workshop.fetch_workshop_file_details(
        workshop_ids=["123", "123", "456", "invalid"]
    )
    assert set(details) == {"123", "456"}
    assert details["123"].preview_url == "https://cdn.example/preview.jpg"
    assert details["456"].preview_url is None
    assert b"itemcount=2" in requests[0].content
    assert (
        await steam_workshop.fetch_workshop_file_details(workshop_ids=["invalid"]) == {}
    )
    for payload in [
        None,
        [],
        {"response": None},
        {"response": {"publishedfiledetails": {}}},
    ]:
        assert steam_workshop._parse_preview_url(payload) is None
    responses.append(
        {
            "response": {
                "publishedfiledetails": [
                    {"preview_url": "https://cdn.example/preview.jpg"}
                ]
            }
        }
    )
    assert (
        await steam_workshop.fetch_workshop_preview_url(workshop_id="123")
        == "https://cdn.example/preview.jpg"
    )
    responses.append(httpx.Response(500))
    assert await steam_workshop.fetch_workshop_preview_url(workshop_id="123") is None
    responses.append(httpx.Response(500))
    assert await steam_workshop.fetch_workshop_file_details(workshop_ids=["123"]) == {}


@pytest.mark.asyncio
async def test_vanilla_tiers_merge_rated_and_impossible_maps(
    db: AsyncSession, mock_api
) -> None:
    responses, _ = mock_api
    db.add_all(
        [
            Map(id=972390, name="kz_tier_contract"),
            Map(id=972391, name="kz_impossible_contract"),
        ]
    )
    await db.flush()
    responses.extend(
        [
            httpx.Response(
                200, text="map name,tp,pro\nkz_tier_contract,2,3\nkz_unknown,1,1\n"
            ),
            httpx.Response(
                200,
                text="Impossible Maps\nkz_impossible_contract\nkz_missing\nnot-a-map\n",
            ),
        ]
    )
    result = await vanilla_tier.load_vanilla_tiers_by_map_id(session=db)
    assert result == {972390: (2, 3), 972391: (0, 0)}
    responses.extend([httpx.Response(200, text=""), httpx.Response(200, text="")])
    assert await vanilla_tier.load_vanilla_tiers_by_map_id(session=db) == {}
    responses.append(httpx.Response(500))
    with pytest.raises(vanilla_tier.VanillaTierSyncError):
        await vanilla_tier.fetch_vanilla_tier_sheet_csv(sheet_name="Map Tiers")


@pytest.mark.asyncio
async def test_video_metadata_and_view_counts_use_valid_upstream_rows(mock_api) -> None:
    responses, _ = mock_api
    responses.extend(
        [
            {
                "items": [
                    None,
                    {"id": "one", "statistics": {"viewCount": "42"}},
                    {"id": 12, "statistics": {}},
                ]
            },
            {"items": [{"id": "UC123"}]},
            {"code": 0, "data": {"stat": {"view": 17}}},
            {"code": 0, "data": {"title": "KZ run"}},
            {"code": 0, "data": [None, {"tag_name": "KZ"}, {"tag_name": 3}]},
        ]
    )
    assert await youtube.fetch_youtube_video_view_counts(["one"]) == {"one": 42}
    assert await youtube.fetch_youtube_channel_id("channel/UC123") == "UC123"
    assert await bilibili.fetch_bilibili_video_view_counts(["BV123"]) == {"BV123": 17}
    assert await bilibili.fetch_bilibili_video_detail("BV123") == {"title": "KZ run"}
    assert await bilibili.fetch_bilibili_video_tags("BV123") == ["KZ"]
    assert await youtube.fetch_youtube_video_view_counts([]) == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,payload",
    [
        (youtube.fetch_youtube_channel_id, {"items": []}),
        (youtube.fetch_youtube_channel_id, {"items": [{"id": None}]}),
        (bilibili.fetch_bilibili_video_detail, {"code": -1}),
        (bilibili.fetch_bilibili_video_detail, {"code": 0, "data": []}),
        (bilibili.fetch_bilibili_video_tags, {"code": -1}),
        (bilibili.fetch_bilibili_video_tags, {"code": 0, "data": {}}),
    ],
)
async def test_video_metadata_rejects_invalid_payloads(
    mock_api, method, payload
) -> None:
    responses, _ = mock_api
    responses.append(payload)
    with pytest.raises(ValueError):
        await method("@test")


@pytest.mark.asyncio
async def test_image_fetches_restrict_sources_and_require_image_responses(
    mock_api,
) -> None:
    responses, _ = mock_api
    with pytest.raises(ValueError, match="not allowed"):
        await live_streams.fetch_live_preview_image("http://example.com/picture")
    with pytest.raises(ValueError, match="not allowed"):
        await live_streams._fetch_stream_keyframe_image("http://example.com/picture")
    responses.append(
        httpx.Response(
            200,
            content=b"picture",
            headers={"content-type": "image/png; charset=binary"},
        )
    )
    assert await live_streams._fetch_stream_keyframe_image(
        "https://example.com/picture"
    ) == (b"picture", "image/png")
    responses.append(
        httpx.Response(200, text="not an image", headers={"content-type": "text/html"})
    )
    with pytest.raises(ValueError, match="did not return an image"):
        await live_streams._fetch_stream_keyframe_image("https://example.com/picture")
    responses.append(
        httpx.Response(200, content=b"preview", headers={"content-type": "image/jpeg"})
    )
    assert await live_streams.fetch_live_preview_image(
        "https://i0.hdslb.com/preview.jpg"
    ) == (b"preview", "image/jpeg")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "player,expected",
    [
        (None, None),
        ({}, None),
        ({"communityvisibilitystate": "bad"}, None),
        ({"communityvisibilitystate": "3"}, True),
        ({"communityvisibilitystate": 1}, False),
    ],
)
async def test_steam_profile_visibility_validates_payloads(
    mock_api, monkeypatch: pytest.MonkeyPatch, player, expected
) -> None:
    from app.services import player_friends

    monkeypatch.setattr(player_friends.settings, "STEAM_API_KEY", "test-steam")
    responses, _ = mock_api
    responses.append({"response": {"players": [player]}})
    assert (
        await player_friends._fetch_steam_profile_is_public(steamid64=123) is expected
    )


@pytest.mark.asyncio
async def test_steam_friends_handles_private_lists_and_malformed_entries(
    mock_api, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime

    from app.services import player_friends

    monkeypatch.setattr(player_friends.settings, "STEAM_API_KEY", "test-steam")
    responses, _ = mock_api
    responses.append(
        {
            "friendslist": {
                "friends": [
                    None,
                    {},
                    {"steamid": "bad"},
                    {"steamid": "123", "friend_since": "1"},
                    {"steamid": "456", "friend_since": "bad"},
                ]
            }
        }
    )
    assert await player_friends._fetch_steam_friends(steamid64=1) == [
        (123, datetime.fromtimestamp(1, UTC)),
        (456, None),
    ]
    responses.append({"friendslist": {"friends": None}})
    assert await player_friends._fetch_steam_friends(steamid64=1) == []
    responses.append(httpx.Response(401))
    with pytest.raises(player_friends.SteamFriendsPrivateError):
        await player_friends._fetch_steam_friends(steamid64=1)
    responses.append(httpx.Response(500))
    assert await player_friends._fetch_steam_profile_is_public(steamid64=1) is None
    monkeypatch.setattr(player_friends.settings, "STEAM_API_KEY", None)
    assert await player_friends._fetch_steam_profile_is_public(steamid64=1) is None
    with pytest.raises(RuntimeError, match="STEAM_API_KEY"):
        await player_friends._fetch_steam_friends(steamid64=1)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["youtube", "bilibili"])
async def test_thumbnail_uploads_cache_images_and_preserve_sources_on_failure(
    mock_api,
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
) -> None:
    module = youtube if provider == "youtube" else bilibili
    upload = AsyncMock(return_value="https://storage.example/cached.jpg")
    monkeypatch.setattr(module.r2_storage, "is_configured", lambda: True)
    monkeypatch.setattr(module.r2_storage, "put_object", upload)
    responses, _ = mock_api
    source = "https://i0.hdslb.com/image.jpg"

    async def cache(raw_url):
        if provider == "youtube":
            return await module.cache_youtube_thumbnail(
                video_id="video123", raw_url=raw_url
            )
        return await module.cache_bilibili_thumbnail(bvid="BV123", raw_url=raw_url)

    assert await cache(None) is None
    responses.append(
        httpx.Response(
            200, content=b"image bytes", headers={"content-type": "image/jpeg"}
        )
    )
    assert await cache(source) == "https://storage.example/cached.jpg"
    assert upload.await_args.kwargs["body"] == b"image bytes"
    assert upload.await_args.kwargs["cache_control"].endswith("immutable")
    responses.append(
        httpx.Response(200, text="bad payload", headers={"content-type": "text/html"})
    )
    assert await cache(source) == source
    monkeypatch.setattr(module.r2_storage, "is_configured", lambda: False)
    assert await cache(source) == source


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload,expected",
    [
        (
            {"response": {"success": 1, "steamid": "76561199022242128"}},
            76561199022242128,
        ),
        ({"response": {"success": 42}}, None),
        ({"response": {}}, None),
        ({"response": []}, None),
    ],
)
async def test_steam_vanity_resolution_validates_service_responses(
    mock_api, monkeypatch: pytest.MonkeyPatch, payload, expected
) -> None:
    from app.crud import player

    monkeypatch.setattr(player.settings, "STEAM_API_KEY", "test-steam")
    responses, _ = mock_api
    responses.append(payload)
    assert (
        await player._resolve_steam_vanity_url_to_steamid64("quality-player")
        == expected
    )
    responses.append(httpx.Response(503))
    assert await player._resolve_steam_vanity_url_to_steamid64("quality-player") is None


@pytest.mark.asyncio
async def test_steam_summary_batching_skips_invalid_rows_and_marks_failures(
    mock_api, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.crud import player

    monkeypatch.setattr(player.settings, "STEAM_API_KEY", "test-steam")
    responses, requests = mock_api
    responses.append(
        {
            "response": {
                "players": [
                    None,
                    {},
                    {"steamid": "bad"},
                    {
                        "steamid": "123",
                        "personaname": "Name",
                        "profileurl": "https://steamcommunity.com/id/quality-player",
                        "avatarfull": "https://avatars.example/"
                        + "a" * 40
                        + "_full.jpg",
                        "loccountrycode": "DE",
                    },
                ]
            }
        }
    )
    result = await player._fetch_players_from_steam_api_if_available([123, 123])
    assert result[123]["name"] == "Name"
    assert result[123]["custom_id"] == "quality-player"
    assert result[123]["avatar_hash"] == "a" * 40
    assert requests[0].url.params["steamids"] == "123"
    assert player._normalize_steam_player_payload(steamid64=123, player=None) is None
    for payload in [{"response": {"players": {}}}, httpx.Response(503)]:
        responses.append(payload)
        assert await player._fetch_players_from_steam_api_if_available([123]) is None
    responses.append({"response": {"players": []}})
    assert (await player._fetch_player_from_steam_api(123))["fetched"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method_name",
    [
        "create_or_update_player_from_steam",
        "create_or_update_player_from_steam_if_fetched",
    ],
)
@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("fail_commit", [False, True])
async def test_steam_identity_updates_preserve_data_after_integrity_races(
    db: AsyncSession,
    mock_api,
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
    existing: bool,
    fail_commit: bool,
) -> None:
    from sqlalchemy.exc import IntegrityError

    from app.crud import player
    from app.models import Player
    from tests.utils.utils import random_steamid64

    monkeypatch.setattr(player.settings, "STEAM_API_KEY", "test-steam")
    steamid = random_steamid64()
    if existing:
        db.add(Player(steamid64=steamid, name="Old name"))
        await db.commit()
    responses, _ = mock_api
    responses.append(
        {
            "response": {
                "players": [
                    {
                        "steamid": str(steamid),
                        "personaname": "Updated name",
                        "profileurl": "https://steamcommunity.com/id/quality-player",
                        "avatarhash": "b" * 40,
                        "loccountrycode": "DE",
                    }
                ]
            }
        }
    )
    if fail_commit:
        original_commit = db.commit
        failed = False

        async def commit():
            nonlocal failed
            if not failed:
                failed = True
                raise IntegrityError(
                    "write", None, Exception("concurrent vanity collision")
                )
            await original_commit()

        monkeypatch.setattr(db, "commit", commit)
    result = await getattr(player, method_name)(session=db, steamid64=steamid)
    identity = result[0] if isinstance(result, tuple) else result
    assert identity.steamid64 == steamid
    assert identity.name == "Updated name"
    assert identity.country == "DE"
    assert identity.avatar_hash == "b" * 40
    assert identity.custom_id == (None if fail_commit else "quality-player")
    stored = await db.get(Player, steamid)
    assert stored.name == "Updated name"


@pytest.mark.asyncio
async def test_websub_subscription_refresh_reports_partial_failures(
    mock_api, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(youtube.settings, "YOUTUBE_WEBSUB_SECRET", "test-secret")
    monkeypatch.setattr(youtube.settings, "YOUTUBE_WEBSUB_ENABLED", True)
    links = [
        PlayerSocialLink(
            player_steamid64=1,
            platform=PlayerSocialPlatform.YOUTUBE,
            account_identifier="channel/UC1",
        ),
        PlayerSocialLink(
            player_steamid64=2,
            platform=PlayerSocialPlatform.YOUTUBE,
            account_identifier="channel/UC2",
        ),
    ]
    responses, requests = mock_api
    responses.extend(
        [
            {"items": [{"id": "UC1"}]},
            httpx.Response(202),
            {"items": [{"id": "UC2"}]},
            httpx.Response(500),
        ]
    )
    assert await youtube.refresh_youtube_websub_subscriptions(links=links) is False
    assert "hub.mode=subscribe" in requests[1].content.decode()


@pytest.mark.asyncio
async def test_twitch_oauth_exchange_and_verified_identity_validate_payloads(
    mock_api,
) -> None:
    from urllib.parse import parse_qs, urlsplit

    from app.services import twitch_social_link_verification as verification

    responses, requests = mock_api
    authorization = verification.build_twitch_authorization_url(
        redirect_uri="https://example.com/callback", state="test-state"
    )
    query = parse_qs(urlsplit(authorization).query)
    assert query["state"] == ["test-state"]
    assert query["redirect_uri"] == ["https://example.com/callback"]
    responses.append({"access_token": "test-access-token"})
    assert (
        await verification.exchange_twitch_code_for_access_token(
            code="test-code", redirect_uri="https://example.com/callback"
        )
        == "test-access-token"
    )
    assert b"grant_type=authorization_code" in requests[-1].content
    for invalid in [None, "", 42]:
        responses.append({"access_token": invalid})
        with pytest.raises(ValueError, match="access token"):
            await verification.exchange_twitch_code_for_access_token(
                code="test-code", redirect_uri="https://example.com/callback"
            )
    responses.append(
        {"data": [{"login": " MixedCase ", "display_name": " Display Name "}]}
    )
    user = await verification.fetch_twitch_authenticated_user(
        access_token="test-access-token"
    )
    assert (
        user.account_identifier == "mixedcase" and user.display_name == "Display Name"
    )
    responses.append({"data": [{"login": "Fallback", "display_name": None}]})
    assert (
        await verification.fetch_twitch_authenticated_user(
            access_token="test-access-token"
        )
    ).display_name == "Fallback"
    for payload in [{"data": []}, {"data": [{"login": None}]}]:
        responses.append(payload)
        with pytest.raises(ValueError):
            await verification.fetch_twitch_authenticated_user(
                access_token="test-access-token"
            )
    error = verification.build_twitch_verification_error_return_url(
        frontend_host="https://example.com",
        return_path="/settings/social-links",
        message="Try again",
    )
    assert parse_qs(urlsplit(error).query)["message"] == ["Try again"]


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, None),
        (True, None),
        (-1, None),
        (30, 30),
        ("P1DT2H3M4S", 93784),
        ("invalid", None),
        ("P", None),
    ],
)
def test_youtube_durations_reject_invalid_metadata(
    raw: object, expected: int | None
) -> None:
    assert youtube._parse_duration(raw) == expected


def test_youtube_dates_and_thumbnails_validate_metadata() -> None:
    from datetime import UTC, datetime

    assert youtube._parse_published(None) is None
    assert youtube._parse_published("invalid") is None
    assert youtube._parse_published("2025-01-01T00:00:00") == datetime(
        2025, 1, 1, tzinfo=UTC
    )
    assert youtube._thumbnail_url({"thumbnails": []}) is None
    assert youtube._thumbnail_url({"thumbnails": {"high": {"url": 42}}}) is None
    assert (
        youtube._thumbnail_url(
            {"thumbnails": {"maxres": {"url": "https://example.com/image.jpg"}}}
        )
        == "https://example.com/image.jpg"
    )
