import uuid
from datetime import UTC, datetime

import pytest

from app.services import bilibili_social_link_verification as verification


def test_create_bilibili_pending_confirmation_token_round_trips() -> None:
    token, verification_code, expires_at = (
        verification.create_bilibili_pending_confirmation_token(
            steamid64=76561198000000001,
            link_id="123e4567-e89b-12d3-a456-426614174000",
            current_account_identifier="123456",
        )
    )

    payload = verification.decode_bilibili_pending_confirmation_token(token)

    assert payload.steamid64 == 76561198000000001
    assert payload.link_id == "123e4567-e89b-12d3-a456-426614174000"
    assert payload.platform == "bilibili"
    assert payload.current_account_identifier == "123456"
    assert payload.verification_code == verification_code
    assert str(uuid.UUID(verification_code)) == verification_code
    assert expires_at > datetime.now(UTC)


def test_parse_bilibili_profile_description_reads_meta_content() -> None:
    html = """
    <html>
      <head>
        <meta charset="UTF-8" />
        <meta name="description" content="Player bio GOKZTOP-BILI-ABC123-DEF456" />
      </head>
    </html>
    """

    description = verification.parse_bilibili_profile_description(html)

    assert description == "Player bio GOKZTOP-BILI-ABC123-DEF456"


def test_parse_bilibili_profile_text_strips_bilibili_boilerplate() -> None:
    html = """
    <html>
      <head>
        <meta
          name="description"
          content="哔哩哔哩碧诗的个人空间，提供碧诗分享的视频、音频、文章、动态、收藏等内容，关注碧诗账号，第一时间了解UP主动态。https://kami.im 直男过气网红 #  We Are Star Dust"
        />
      </head>
    </html>
    """

    profile_text = verification.parse_bilibili_profile_text(html)

    assert profile_text == "https://kami.im 直男过气网红 #  We Are Star Dust"


def test_parse_bilibili_profile_description_returns_none_without_meta() -> None:
    description = verification.parse_bilibili_profile_description("<html></html>")

    assert description is None


@pytest.mark.asyncio
async def test_verify_bilibili_profile_contains_code_accepts_matching_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    html = """
    <html>
      <head>
        <meta
          name="description"
          content="哔哩哔哩用户的个人空间，提供用户分享的视频、音频、文章、动态、收藏等内容，关注用户账号，第一时间了解UP主动态。hello GOKZTOP-BILI-ABC123-DEF456 world"
        />
      </head>
    </html>
    """

    class _Response:
        text = html

        def raise_for_status(self) -> None:
            return None

    class _Client:
        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def get(self, url: str) -> _Response:
            assert url == "https://space.bilibili.com/123456"
            return _Response()

    monkeypatch.setattr(verification.httpx, "AsyncClient", lambda **_: _Client())

    await verification.verify_bilibili_profile_contains_code(
        account_identifier="123456",
        verification_code="GOKZTOP-BILI-ABC123-DEF456",
    )


@pytest.mark.asyncio
async def test_verify_bilibili_profile_contains_code_rejects_missing_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    html = """
    <html>
      <head>
        <meta
          name="description"
          content="哔哩哔哩用户的个人空间，提供用户分享的视频、音频、文章、动态、收藏等内容，关注用户账号，第一时间了解UP主动态。missing code here"
        />
      </head>
    </html>
    """

    class _Response:
        text = html

        def raise_for_status(self) -> None:
            return None

    class _Client:
        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def get(self, _url: str) -> _Response:
            return _Response()

    monkeypatch.setattr(verification.httpx, "AsyncClient", lambda **_: _Client())

    with pytest.raises(verification.BilibiliProfileVerificationCodeMissingError):
        await verification.verify_bilibili_profile_contains_code(
            account_identifier="123456",
            verification_code="GOKZTOP-BILI-ABC123-DEF456",
        )
