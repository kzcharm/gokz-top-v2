from datetime import UTC, datetime
from pathlib import Path

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


def test_r2_storage_public_url_to_key_decodes_managed_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_r2_settings(monkeypatch)

    assert (
        r2_storage.public_url_to_key(
            "https://cdn.example.com/assets/live/keyframes/twitch/frame%201.jpg"
        )
        == "live/keyframes/twitch/frame 1.jpg"
    )
    assert (
        r2_storage.public_url_to_key(
            "https://other.example.com/assets/live/keyframes/frame.jpg"
        )
        is None
    )
    assert (
        r2_storage.public_url_to_key(
            "https://cdn.example.com/other/live/keyframes/frame.jpg"
        )
        is None
    )
    assert (
        r2_storage.public_url_to_key(
            "https://cdn.example.com/assets/live/keyframes/../secret.jpg"
        )
        is None
    )


@pytest.mark.asyncio
async def test_r2_storage_list_objects_paginates_and_signs_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_r2_settings(monkeypatch)
    requests: list[tuple[str, dict[str, str]]] = []
    pages = [
        b"""<?xml version="1.0" encoding="UTF-8"?>
        <ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
          <IsTruncated>true</IsTruncated>
          <NextContinuationToken>next/+ token</NextContinuationToken>
          <Contents><Key>live/keyframes/a.jpg</Key><LastModified>2026-08-30T10:00:00Z</LastModified></Contents>
        </ListBucketResult>""",
        b"""<?xml version="1.0" encoding="UTF-8"?>
        <ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
          <IsTruncated>false</IsTruncated>
          <Contents><Key>live/keyframes/b.jpg</Key><LastModified>2026-08-30T11:00:00+00:00</LastModified></Contents>
        </ListBucketResult>""",
    ]

    class _FakeAsyncClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def __aenter__(self) -> _FakeAsyncClient:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def get(
            self,
            url: str,
            *,
            headers: dict[str, str],
        ) -> httpx.Response:
            requests.append((url, headers))
            return httpx.Response(
                status_code=200,
                content=pages[len(requests) - 1],
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(r2_storage.httpx, "AsyncClient", _FakeAsyncClient)

    objects = await r2_storage.list_objects(prefix="/live/keyframes/")

    assert objects == [
        r2_storage.R2Object(
            "live/keyframes/a.jpg",
            datetime(2026, 8, 30, 10, tzinfo=UTC),
        ),
        r2_storage.R2Object(
            "live/keyframes/b.jpg",
            datetime(2026, 8, 30, 11, tzinfo=UTC),
        ),
    ]
    assert requests[0][0].endswith("?list-type=2&prefix=live%2Fkeyframes%2F")
    assert requests[1][0].endswith(
        "?continuation-token=next%2F%2B%20token&list-type=2&prefix=live%2Fkeyframes%2F"
    )
    for _url, headers in requests:
        assert headers["host"] == "account.r2.cloudflarestorage.com"
        assert headers["authorization"].startswith(
            "AWS4-HMAC-SHA256 Credential=access-key/"
        )


@pytest.mark.asyncio
async def test_r2_storage_list_objects_rejects_truncated_page_without_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_r2_settings(monkeypatch)

    class _FakeAsyncClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def __aenter__(self) -> _FakeAsyncClient:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def get(
            self,
            url: str,
            *,
            headers: dict[str, str],
        ) -> httpx.Response:
            return httpx.Response(
                status_code=200,
                content=b"<ListBucketResult><IsTruncated>true</IsTruncated></ListBucketResult>",
                request=httpx.Request("GET", url, headers=headers),
            )

    monkeypatch.setattr(r2_storage.httpx, "AsyncClient", _FakeAsyncClient)

    with pytest.raises(RuntimeError, match="without a continuation token"):
        await r2_storage.list_objects(prefix="live/keyframes/")


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

    assert (
        public_url == "https://cdn.example.com/assets/live/keyframes/twitch/link-id.jpg"
    )
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


@pytest.mark.asyncio
async def test_r2_storage_put_file_streams_small_files_with_async_content(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _set_r2_settings(monkeypatch)
    monkeypatch.setattr(settings, "R2_MULTIPART_UPLOAD_THRESHOLD_BYTES", 1024)
    bsp_path = tmp_path / "kz_test.bsp"
    bsp_path.write_bytes(b"small-bsp-file")
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
            content: object,
            headers: dict[str, str],
        ) -> httpx.Response:
            chunks: list[bytes] = []
            assert hasattr(content, "__aiter__")
            async for chunk in content:  # type: ignore[union-attr]
                chunks.append(chunk)
            captured_request["url"] = url
            captured_request["content"] = b"".join(chunks)
            captured_request["headers"] = headers
            return httpx.Response(
                status_code=200,
                request=httpx.Request("PUT", url),
            )

    monkeypatch.setattr(r2_storage.httpx, "AsyncClient", _FakeAsyncClient)

    public_url = await r2_storage.put_file(
        key="maps/kz_test.bsp",
        path=bsp_path,
        content_type="application/octet-stream",
        cache_control="public, max-age=31536000, immutable",
    )

    assert public_url == "https://cdn.example.com/assets/maps/kz_test.bsp"
    assert (
        captured_request["url"]
        == "https://account.r2.cloudflarestorage.com/bucket/maps/kz_test.bsp"
    )
    assert captured_request["content"] == b"small-bsp-file"
    headers = captured_request["headers"]
    assert isinstance(headers, dict)
    assert headers["content-length"] == "14"
    assert headers["content-type"] == "application/octet-stream"


@pytest.mark.asyncio
async def test_r2_storage_put_file_uses_multipart_for_large_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _set_r2_settings(monkeypatch)
    monkeypatch.setattr(settings, "R2_MULTIPART_UPLOAD_THRESHOLD_BYTES", 4)
    monkeypatch.setattr(settings, "R2_MULTIPART_PART_SIZE_BYTES", 5 * 1024 * 1024)
    package_path = tmp_path / "GlobalMaps.7z"
    package_path.write_bytes((b"a" * (5 * 1024 * 1024)) + b"bbb")
    captured_requests: list[dict[str, object]] = []

    class _FakeAsyncClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def __aenter__(self) -> _FakeAsyncClient:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def post(
            self,
            url: str,
            *,
            headers: dict[str, str],
            content: bytes,
        ) -> httpx.Response:
            captured_requests.append(
                {"method": "POST", "url": url, "headers": headers, "content": content}
            )
            if url.endswith("?uploads="):
                return httpx.Response(
                    status_code=200,
                    content=b"<InitiateMultipartUploadResult><UploadId>upload-1</UploadId></InitiateMultipartUploadResult>",
                    request=httpx.Request("POST", url),
                )
            return httpx.Response(status_code=200, request=httpx.Request("POST", url))

        async def put(
            self,
            url: str,
            *,
            headers: dict[str, str],
            content: bytes,
        ) -> httpx.Response:
            captured_requests.append(
                {"method": "PUT", "url": url, "headers": headers, "content": content}
            )
            part_number = "1" if "partNumber=1" in url else "2"
            return httpx.Response(
                status_code=200,
                headers={"etag": f'"etag-{part_number}"'},
                request=httpx.Request("PUT", url),
            )

        async def delete(
            self,
            url: str,
            *,
            headers: dict[str, str],
        ) -> httpx.Response:
            captured_requests.append(
                {"method": "DELETE", "url": url, "headers": headers}
            )
            return httpx.Response(status_code=204, request=httpx.Request("DELETE", url))

    monkeypatch.setattr(r2_storage.httpx, "AsyncClient", _FakeAsyncClient)

    public_url = await r2_storage.put_file(
        key="packages/GlobalMaps.7z",
        path=package_path,
        content_type="application/x-7z-compressed",
        cache_control="public, max-age=3600",
    )

    assert public_url == "https://cdn.example.com/assets/packages/GlobalMaps.7z"
    assert [request["method"] for request in captured_requests] == [
        "POST",
        "PUT",
        "PUT",
        "POST",
    ]
    assert (
        captured_requests[0]["url"]
        == "https://account.r2.cloudflarestorage.com/bucket/packages/GlobalMaps.7z?uploads="
    )
    assert (
        captured_requests[1]["url"]
        == "https://account.r2.cloudflarestorage.com/bucket/packages/GlobalMaps.7z?partNumber=1&uploadId=upload-1"
    )
    assert (
        captured_requests[2]["url"]
        == "https://account.r2.cloudflarestorage.com/bucket/packages/GlobalMaps.7z?partNumber=2&uploadId=upload-1"
    )
    assert (
        captured_requests[3]["url"]
        == "https://account.r2.cloudflarestorage.com/bucket/packages/GlobalMaps.7z?uploadId=upload-1"
    )
    complete_body = captured_requests[3]["content"]
    assert isinstance(complete_body, bytes)
    assert b"<PartNumber>1</PartNumber>" in complete_body
    assert b'<ETag>"etag-2"</ETag>' in complete_body
