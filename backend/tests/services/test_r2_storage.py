import httpx
import pytest

from app.core.config import settings
from app.services import r2_storage


def _set_r2_settings(
    monkeypatch: pytest.MonkeyPatch,
    *,
    account_id: str | None = "account",
    access_key_id: str | None = "access-key",
    secret_access_key: str | None = "secret-key",
    bucket_name: str | None = "bucket",
    public_base_url: str | None = "https://cdn.example.com/assets/",
) -> None:
    monkeypatch.setattr(settings, "R2_ACCOUNT_ID", account_id)
    monkeypatch.setattr(settings, "R2_ACCESS_KEY_ID", access_key_id)
    monkeypatch.setattr(settings, "R2_SECRET_ACCESS_KEY", secret_access_key)
    monkeypatch.setattr(settings, "R2_BUCKET_NAME", bucket_name)
    monkeypatch.setattr(settings, "R2_PUBLIC_BASE_URL", public_base_url)


def test_r2_storage_config_requires_all_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_r2_settings(monkeypatch, public_base_url=None)

    assert r2_storage.get_r2_storage_config() is None
    assert r2_storage.is_configured() is False


def test_r2_storage_build_public_url_quotes_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_r2_settings(monkeypatch)

    assert (
        r2_storage.build_public_url("/live/keyframes/bilibili/frame 1.jpg")
        == "https://cdn.example.com/assets/live/keyframes/bilibili/frame%201.jpg"
    )


@pytest.mark.asyncio
async def test_r2_storage_put_object_signs_and_uploads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_r2_settings(monkeypatch)
    captured_request: dict[str, object] = {}

    class _FakeAsyncClient:
        def __init__(self, **kwargs: object) -> None:
            captured_request["client_kwargs"] = kwargs

        async def __aenter__(self) -> _FakeAsyncClient:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def put(
            self,
            url: str,
            *,
            content: bytes,
            headers: dict[str, str],
        ) -> httpx.Response:
            captured_request["url"] = url
            captured_request["content"] = content
            captured_request["headers"] = headers
            return httpx.Response(
                status_code=200,
                request=httpx.Request("PUT", url),
            )

    monkeypatch.setattr(r2_storage.httpx, "AsyncClient", _FakeAsyncClient)

    public_url = await r2_storage.put_object(
        key="live/keyframes/twitch/link-id.jpg",
        body=b"image-bytes",
        content_type="image/jpeg",
        cache_control="public, max-age=31536000, immutable",
    )

    assert public_url == "https://cdn.example.com/assets/live/keyframes/twitch/link-id.jpg"
    assert (
        captured_request["url"]
        == "https://account.r2.cloudflarestorage.com/bucket/live/keyframes/twitch/link-id.jpg"
    )
    assert captured_request["content"] == b"image-bytes"
    headers = captured_request["headers"]
    assert isinstance(headers, dict)
    assert headers["content-type"] == "image/jpeg"
    assert headers["cache-control"] == "public, max-age=31536000, immutable"
    assert headers["host"] == "account.r2.cloudflarestorage.com"
    assert headers["x-amz-content-sha256"]
    assert headers["x-amz-date"]
    assert headers["authorization"].startswith(
        "AWS4-HMAC-SHA256 Credential=access-key/"
    )
