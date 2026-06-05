from __future__ import annotations

import asyncio
import hashlib
import hmac
from collections.abc import AsyncIterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote
from xml.etree import ElementTree

import httpx

from app.core.config import settings

R2_REGION = "auto"
R2_SERVICE = "s3"
R2_SIGNATURE_ALGORITHM = "AWS4-HMAC-SHA256"


@dataclass(frozen=True, slots=True)
class R2StorageConfig:
    account_id: str
    access_key_id: str
    secret_access_key: str
    bucket_name: str
    public_base_url: str


def get_r2_storage_config() -> R2StorageConfig | None:
    required_values = (
        settings.R2_ACCOUNT_ID,
        settings.R2_ACCESS_KEY_ID,
        settings.R2_SECRET_ACCESS_KEY,
        settings.R2_BUCKET_NAME,
        settings.R2_PUBLIC_BASE_URL,
    )
    if not all(value and value.strip() for value in required_values):
        return None

    return R2StorageConfig(
        account_id=settings.R2_ACCOUNT_ID or "",
        access_key_id=settings.R2_ACCESS_KEY_ID or "",
        secret_access_key=settings.R2_SECRET_ACCESS_KEY or "",
        bucket_name=settings.R2_BUCKET_NAME or "",
        public_base_url=settings.R2_PUBLIC_BASE_URL or "",
    )


def is_configured() -> bool:
    return get_r2_storage_config() is not None


def build_public_url(key: str, *, config: R2StorageConfig | None = None) -> str:
    storage_config = config or get_r2_storage_config()
    if storage_config is None:
        raise RuntimeError("Cloudflare R2 storage is not configured")

    return (
        f"{storage_config.public_base_url.rstrip('/')}/"
        f"{quote(key.lstrip('/'), safe='/')}"
    )


async def put_object(
    *,
    key: str,
    body: bytes,
    content_type: str,
    cache_control: str | None = None,
) -> str:
    storage_config = get_r2_storage_config()
    if storage_config is None:
        raise RuntimeError("Cloudflare R2 storage is not configured")

    normalized_key = key.lstrip("/")
    encoded_key = quote(normalized_key, safe="/")
    host = f"{storage_config.account_id}.r2.cloudflarestorage.com"
    canonical_uri = f"/{storage_config.bucket_name}/{encoded_key}"
    url = f"https://{host}{canonical_uri}"
    payload_hash = hashlib.sha256(body).hexdigest()
    now = datetime.now(UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    headers = {
        "content-type": content_type,
        "host": host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    if cache_control is not None:
        headers["cache-control"] = cache_control

    authorization = _build_authorization_header(
        config=storage_config,
        method="PUT",
        canonical_uri=canonical_uri,
        headers=headers,
        payload_hash=payload_hash,
        date_stamp=date_stamp,
        amz_date=amz_date,
    )
    request_headers = dict(headers)
    request_headers["authorization"] = authorization

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.put(url, content=body, headers=request_headers)
        response.raise_for_status()

    return build_public_url(normalized_key, config=storage_config)


async def put_file(
    *,
    key: str,
    path: Path,
    content_type: str,
    cache_control: str | None = None,
) -> str:
    storage_config = get_r2_storage_config()
    if storage_config is None:
        raise RuntimeError("Cloudflare R2 storage is not configured")

    file_size = path.stat().st_size
    if file_size >= settings.R2_MULTIPART_UPLOAD_THRESHOLD_BYTES:
        return await _put_file_multipart(
            config=storage_config,
            key=key,
            path=path,
            content_type=content_type,
            cache_control=cache_control,
        )

    payload_hash = hash_file_sha256(path)
    return await _put_object_with_payload_hash(
        config=storage_config,
        key=key,
        content=_aiter_file_chunks(path),
        payload_hash=payload_hash,
        content_length=file_size,
        content_type=content_type,
        cache_control=cache_control,
    )


async def delete_object(*, key: str) -> None:
    storage_config = get_r2_storage_config()
    if storage_config is None:
        raise RuntimeError("Cloudflare R2 storage is not configured")

    normalized_key = key.lstrip("/")
    encoded_key = quote(normalized_key, safe="/")
    host = f"{storage_config.account_id}.r2.cloudflarestorage.com"
    canonical_uri = f"/{storage_config.bucket_name}/{encoded_key}"
    url = f"https://{host}{canonical_uri}"
    payload_hash = hashlib.sha256(b"").hexdigest()
    now = datetime.now(UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    headers = {
        "host": host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    authorization = _build_authorization_header(
        config=storage_config,
        method="DELETE",
        canonical_uri=canonical_uri,
        headers=headers,
        payload_hash=payload_hash,
        date_stamp=date_stamp,
        amz_date=amz_date,
    )
    request_headers = dict(headers)
    request_headers["authorization"] = authorization

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.delete(url, headers=request_headers)
        response.raise_for_status()


def hash_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def _aiter_file_chunks(path: Path) -> AsyncIterable[bytes]:
    with path.open("rb") as file_obj:
        while chunk := await asyncio.to_thread(file_obj.read, 1024 * 1024):
            yield chunk


async def _put_object_with_payload_hash(
    *,
    config: R2StorageConfig,
    key: str,
    content: bytes | AsyncIterable[bytes],
    payload_hash: str,
    content_length: int | None = None,
    content_type: str,
    cache_control: str | None,
) -> str:
    normalized_key = key.lstrip("/")
    encoded_key = quote(normalized_key, safe="/")
    host = f"{config.account_id}.r2.cloudflarestorage.com"
    canonical_uri = f"/{config.bucket_name}/{encoded_key}"
    url = f"https://{host}{canonical_uri}"

    headers = {
        "content-type": content_type,
        "host": host,
    }
    if content_length is not None:
        headers["content-length"] = str(content_length)
    if cache_control is not None:
        headers["cache-control"] = cache_control

    request_headers = _build_signed_headers(
        config=config,
        method="PUT",
        canonical_uri=canonical_uri,
        headers=headers,
        payload_hash=payload_hash,
    )

    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.put(url, content=content, headers=request_headers)
        response.raise_for_status()

    return build_public_url(normalized_key, config=config)


async def _put_file_multipart(
    *,
    config: R2StorageConfig,
    key: str,
    path: Path,
    content_type: str,
    cache_control: str | None,
) -> str:
    normalized_key = key.lstrip("/")
    encoded_key = quote(normalized_key, safe="/")
    host = f"{config.account_id}.r2.cloudflarestorage.com"
    canonical_uri = f"/{config.bucket_name}/{encoded_key}"
    timeout = httpx.Timeout(connect=30.0, read=900.0, write=900.0, pool=30.0)
    upload_id: str | None = None
    parts: list[tuple[int, str]] = []

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            upload_id = await _create_multipart_upload(
                client=client,
                config=config,
                host=host,
                canonical_uri=canonical_uri,
                content_type=content_type,
                cache_control=cache_control,
            )
            part_size = max(settings.R2_MULTIPART_PART_SIZE_BYTES, 5 * 1024 * 1024)
            with path.open("rb") as file_obj:
                part_number = 1
                while True:
                    chunk = await asyncio.to_thread(file_obj.read, part_size)
                    if not chunk:
                        break
                    etag = await _upload_multipart_part(
                        client=client,
                        config=config,
                        host=host,
                        canonical_uri=canonical_uri,
                        upload_id=upload_id,
                        part_number=part_number,
                        body=chunk,
                    )
                    parts.append((part_number, etag))
                    part_number += 1

            if not parts:
                raise RuntimeError("Cannot multipart upload an empty file")

            await _complete_multipart_upload(
                client=client,
                config=config,
                host=host,
                canonical_uri=canonical_uri,
                upload_id=upload_id,
                parts=parts,
            )
        except Exception:
            if upload_id is not None:
                await _abort_multipart_upload(
                    client=client,
                    config=config,
                    host=host,
                    canonical_uri=canonical_uri,
                    upload_id=upload_id,
                )
            raise

    return build_public_url(normalized_key, config=config)


async def _create_multipart_upload(
    *,
    client: httpx.AsyncClient,
    config: R2StorageConfig,
    host: str,
    canonical_uri: str,
    content_type: str,
    cache_control: str | None,
) -> str:
    query_string = _canonical_query_string({"uploads": ""})
    headers = {
        "content-type": content_type,
        "host": host,
    }
    if cache_control is not None:
        headers["cache-control"] = cache_control
    request_headers = _build_signed_headers(
        config=config,
        method="POST",
        canonical_uri=canonical_uri,
        headers=headers,
        payload_hash=hashlib.sha256(b"").hexdigest(),
        canonical_query_string=query_string,
    )
    response = await client.post(
        _build_url(host=host, canonical_uri=canonical_uri, query_string=query_string),
        headers=request_headers,
        content=b"",
    )
    response.raise_for_status()
    upload_id = _find_xml_text(response.content, "UploadId")
    if not upload_id:
        raise RuntimeError("R2 did not return an UploadId for multipart upload")
    return upload_id


async def _upload_multipart_part(
    *,
    client: httpx.AsyncClient,
    config: R2StorageConfig,
    host: str,
    canonical_uri: str,
    upload_id: str,
    part_number: int,
    body: bytes,
) -> str:
    query_string = _canonical_query_string(
        {"partNumber": str(part_number), "uploadId": upload_id}
    )
    payload_hash = hashlib.sha256(body).hexdigest()
    request_headers = _build_signed_headers(
        config=config,
        method="PUT",
        canonical_uri=canonical_uri,
        headers={
            "content-length": str(len(body)),
            "host": host,
        },
        payload_hash=payload_hash,
        canonical_query_string=query_string,
    )
    response = await client.put(
        _build_url(host=host, canonical_uri=canonical_uri, query_string=query_string),
        headers=request_headers,
        content=body,
    )
    response.raise_for_status()
    etag = response.headers.get("etag")
    if not etag:
        raise RuntimeError(f"R2 did not return an ETag for multipart part {part_number}")
    return etag


async def _complete_multipart_upload(
    *,
    client: httpx.AsyncClient,
    config: R2StorageConfig,
    host: str,
    canonical_uri: str,
    upload_id: str,
    parts: Sequence[tuple[int, str]],
) -> None:
    query_string = _canonical_query_string({"uploadId": upload_id})
    body = _build_complete_multipart_body(parts)
    request_headers = _build_signed_headers(
        config=config,
        method="POST",
        canonical_uri=canonical_uri,
        headers={
            "content-length": str(len(body)),
            "content-type": "application/xml",
            "host": host,
        },
        payload_hash=hashlib.sha256(body).hexdigest(),
        canonical_query_string=query_string,
    )
    response = await client.post(
        _build_url(host=host, canonical_uri=canonical_uri, query_string=query_string),
        headers=request_headers,
        content=body,
    )
    response.raise_for_status()


async def _abort_multipart_upload(
    *,
    client: httpx.AsyncClient,
    config: R2StorageConfig,
    host: str,
    canonical_uri: str,
    upload_id: str,
) -> None:
    query_string = _canonical_query_string({"uploadId": upload_id})
    request_headers = _build_signed_headers(
        config=config,
        method="DELETE",
        canonical_uri=canonical_uri,
        headers={"host": host},
        payload_hash=hashlib.sha256(b"").hexdigest(),
        canonical_query_string=query_string,
    )
    response = await client.delete(
        _build_url(host=host, canonical_uri=canonical_uri, query_string=query_string),
        headers=request_headers,
    )
    response.raise_for_status()


def _build_signed_headers(
    *,
    config: R2StorageConfig,
    method: str,
    canonical_uri: str,
    headers: dict[str, str],
    payload_hash: str,
    canonical_query_string: str = "",
) -> dict[str, str]:
    now = datetime.now(UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    request_headers = dict(headers)
    request_headers["x-amz-content-sha256"] = payload_hash
    request_headers["x-amz-date"] = amz_date
    request_headers["authorization"] = _build_authorization_header(
        config=config,
        method=method,
        canonical_uri=canonical_uri,
        headers=request_headers,
        payload_hash=payload_hash,
        date_stamp=date_stamp,
        amz_date=amz_date,
        canonical_query_string=canonical_query_string,
    )
    return request_headers


def _canonical_query_string(params: dict[str, str]) -> str:
    return "&".join(
        f"{quote(name, safe='-_.~')}={quote(value, safe='-_.~')}"
        for name, value in sorted(params.items())
    )


def _build_url(*, host: str, canonical_uri: str, query_string: str) -> str:
    return f"https://{host}{canonical_uri}?{query_string}"


def _find_xml_text(body: bytes, tag_suffix: str) -> str | None:
    root = ElementTree.fromstring(body)
    for element in root.iter():
        if element.tag.endswith(tag_suffix):
            return element.text
    return None


def _build_complete_multipart_body(parts: Sequence[tuple[int, str]]) -> bytes:
    root = ElementTree.Element("CompleteMultipartUpload")
    for part_number, etag in parts:
        part = ElementTree.SubElement(root, "Part")
        ElementTree.SubElement(part, "PartNumber").text = str(part_number)
        ElementTree.SubElement(part, "ETag").text = etag
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)


def _build_authorization_header(
    *,
    config: R2StorageConfig,
    method: str,
    canonical_uri: str,
    headers: dict[str, str],
    payload_hash: str,
    date_stamp: str,
    amz_date: str,
    canonical_query_string: str = "",
) -> str:
    canonical_headers, signed_headers = _canonicalize_headers(headers)
    credential_scope = f"{date_stamp}/{R2_REGION}/{R2_SERVICE}/aws4_request"
    canonical_request = "\n".join(
        [
            method,
            canonical_uri,
            canonical_query_string,
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )
    string_to_sign = "\n".join(
        [
            R2_SIGNATURE_ALGORITHM,
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ]
    )
    signature = hmac.new(
        _get_signature_key(config.secret_access_key, date_stamp),
        string_to_sign.encode(),
        hashlib.sha256,
    ).hexdigest()
    return (
        f"{R2_SIGNATURE_ALGORITHM} "
        f"Credential={config.access_key_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )


def _canonicalize_headers(headers: dict[str, str]) -> tuple[str, str]:
    normalized = {
        name.lower().strip(): " ".join(value.strip().split())
        for name, value in headers.items()
    }
    ordered_names = sorted(normalized)
    canonical_headers = "".join(
        f"{name}:{normalized[name]}\n" for name in ordered_names
    )
    return canonical_headers, ";".join(ordered_names)


def _get_signature_key(secret_access_key: str, date_stamp: str) -> bytes:
    date_key = _sign(f"AWS4{secret_access_key}".encode(), date_stamp)
    region_key = _sign(date_key, R2_REGION)
    service_key = _sign(region_key, R2_SERVICE)
    return _sign(service_key, "aws4_request")


def _sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode(), hashlib.sha256).digest()
