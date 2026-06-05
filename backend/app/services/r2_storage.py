from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote

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


def _build_authorization_header(
    *,
    config: R2StorageConfig,
    method: str,
    canonical_uri: str,
    headers: dict[str, str],
    payload_hash: str,
    date_stamp: str,
    amz_date: str,
) -> str:
    canonical_headers, signed_headers = _canonicalize_headers(headers)
    credential_scope = f"{date_stamp}/{R2_REGION}/{R2_SERVICE}/aws4_request"
    canonical_request = "\n".join(
        [
            method,
            canonical_uri,
            "",
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
