import pytest

from app.core.config import settings
from app.services import youtube_social_link_verification as verification


def test_create_youtube_verification_state_token_round_trips() -> None:
    token = verification.create_youtube_verification_state_token(
        steamid64=76561198000000001,
        link_id="123e4567-e89b-12d3-a456-426614174000",
        return_path="/settings?tab=social-links",
        mode="verify",
    )

    payload = verification.decode_youtube_verification_state_token(token)

    assert payload.steamid64 == 76561198000000001
    assert payload.link_id == "123e4567-e89b-12d3-a456-426614174000"
    assert payload.platform == "youtube"
    assert payload.return_path == "/settings?tab=social-links"
    assert payload.mode == "verify"


def test_build_youtube_authorization_url_uses_google_oauth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "YOUTUBE_CLIENT_ID", "youtube-client")
    monkeypatch.setattr(settings, "YOUTUBE_CLIENT_SECRET", "youtube-secret")

    url = verification.build_youtube_authorization_url(
        redirect_uri="https://api.example.com/v1/social-link-verifications/youtube/callback",
        state="state-token",
    )

    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "client_id=youtube-client" in url
    assert "response_type=code" in url
    assert "state=state-token" in url
    assert "scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fyoutube.readonly" in url


@pytest.mark.asyncio
async def test_fetch_youtube_authenticated_channels_parses_channel_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "items": [
                    {
                        "id": "UC12345678901234567890AB",
                        "snippet": {
                            "title": "KZ Streamer",
                            "customUrl": "@KZStreamer",
                        },
                    }
                ]
            }

    class _Client:
        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def get(
            self,
            url: str,
            *,
            params: dict[str, object],
            headers: dict[str, str],
        ) -> _Response:
            assert url == "https://www.googleapis.com/youtube/v3/channels"
            assert params == {"part": "snippet", "mine": "true", "maxResults": 50}
            assert headers == {"Authorization": "Bearer access-token"}
            return _Response()

    monkeypatch.setattr(verification.httpx, "AsyncClient", lambda **_: _Client())

    channels = await verification.fetch_youtube_authenticated_channels(
        access_token="access-token"
    )

    assert len(channels) == 1
    assert channels[0].account_identifier == "channel/UC12345678901234567890AB"
    assert channels[0].display_name == "KZ Streamer"
    assert "@kzstreamer" in channels[0].matching_identifiers
    assert "channel/UC12345678901234567890AB" in channels[0].matching_identifiers


def test_find_matching_youtube_channel_matches_handle_or_channel_id() -> None:
    channel = verification.YoutubeAuthenticatedChannel(
        account_identifier="channel/UC12345678901234567890AB",
        display_name="KZ Streamer",
        matching_identifiers=frozenset(
            {"channel/UC12345678901234567890AB", "@kzstreamer"}
        ),
    )

    assert (
        verification.find_matching_youtube_channel(
            channels=[channel],
            account_identifier="@KZStreamer",
        )
        == channel
    )
    assert (
        verification.find_matching_youtube_channel(
            channels=[channel],
            account_identifier="channel/UC12345678901234567890AB",
        )
        == channel
    )
    assert (
        verification.find_matching_youtube_channel(
            channels=[channel],
            account_identifier="@other",
        )
        is None
    )
