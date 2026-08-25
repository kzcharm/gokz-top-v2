import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from cryptography.fernet import Fernet, InvalidToken
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.models import QQBindingCodePublic, QQBindingSecretPublic, QQBindingTokenPayload

QQ_BIND_TOKEN_PREFIX = "KZTOP"
QQ_BIND_TOKEN_EXPIRE_SECONDS = 600
QQ_BIND_TOKEN_SUFFIX_LENGTH = 22
_QQ_BIND_TOKEN_STEAMID64_BASE = 76561197960265728
_QQ_BIND_TOKEN_PAYLOAD_LENGTH = 8
_QQ_BIND_TOKEN_SIGNATURE_LENGTH = 8
_QQ_BIND_TOKEN_RAW_LENGTH = (
    _QQ_BIND_TOKEN_PAYLOAD_LENGTH + _QQ_BIND_TOKEN_SIGNATURE_LENGTH
)
_BASE62_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def generate_qq_binding_secret() -> str:
    return secrets.token_urlsafe(32)


def encrypt_qq_binding_secret(secret: str) -> str:
    return _get_fernet().encrypt(secret.encode("utf-8")).decode("utf-8")


def decrypt_qq_binding_secret(encrypted_secret: str) -> str:
    try:
        return _get_fernet().decrypt(encrypted_secret.encode("utf-8")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise ValueError("QQ binding secret cannot be decrypted") from exc


async def get_active_qq_binding_secret(*, session: AsyncSession) -> str:
    stored_secret = await crud.get_qq_binding_secret(session=session)
    if stored_secret is None:
        raise ValueError("QQ binding code generation is not configured")
    return decrypt_qq_binding_secret(stored_secret.encrypted_secret)


async def verify_qq_bot_api_key(*, session: AsyncSession, api_key: str) -> bool:
    """Return whether an API key matches the currently active QQ bot secret."""
    try:
        secret = await get_active_qq_binding_secret(session=session)
    except ValueError:
        return False
    return hmac.compare_digest(api_key, secret)


async def create_qq_binding_code(
    *,
    session: AsyncSession,
    steamid64: int | str,
    now: datetime | None = None,
) -> QQBindingCodePublic:
    secret = await get_active_qq_binding_secret(session=session)
    issued_at = (now or datetime.now(UTC)).astimezone(UTC)
    expires_at = issued_at + timedelta(seconds=QQ_BIND_TOKEN_EXPIRE_SECONDS)
    payload = QQBindingTokenPayload(
        steamid64=str(steamid64),
        exp=int(expires_at.timestamp()),
    )
    payload_bytes = _pack_payload(payload)
    signature_bytes = _sign_payload(payload_bytes, secret=secret)
    code = f"{QQ_BIND_TOKEN_PREFIX}{_base62_encode(payload_bytes + signature_bytes)}"
    return QQBindingCodePublic(code=code, expires_at=expires_at)


async def verify_qq_binding_code(
    *,
    session: AsyncSession,
    code: str,
    now: datetime | None = None,
) -> QQBindingTokenPayload:
    secret = await get_active_qq_binding_secret(session=session)
    if not code.startswith(QQ_BIND_TOKEN_PREFIX):
        raise ValueError("Invalid QQ binding code prefix")

    encoded_body = code.removeprefix(QQ_BIND_TOKEN_PREFIX)
    raw_bytes = _base62_decode(
        encoded_body,
        encoded_length=QQ_BIND_TOKEN_SUFFIX_LENGTH,
        decoded_length=_QQ_BIND_TOKEN_RAW_LENGTH,
    )
    payload_bytes = raw_bytes[:_QQ_BIND_TOKEN_PAYLOAD_LENGTH]
    provided_signature_bytes = raw_bytes[_QQ_BIND_TOKEN_PAYLOAD_LENGTH:]
    expected_signature_bytes = _sign_payload(payload_bytes, secret=secret)
    if not hmac.compare_digest(provided_signature_bytes, expected_signature_bytes):
        raise ValueError("Invalid QQ binding code signature")

    payload = _unpack_payload(payload_bytes)
    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    if payload.exp < int(current_time.timestamp()):
        raise ValueError("QQ binding code has expired")
    return payload


def reveal_qq_binding_secret(*, encrypted_secret: str) -> QQBindingSecretPublic:
    return QQBindingSecretPublic(secret=decrypt_qq_binding_secret(encrypted_secret))


def _get_fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)


def _sign_payload(payload_bytes: bytes, *, secret: str) -> bytes:
    return hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).digest()[:_QQ_BIND_TOKEN_SIGNATURE_LENGTH]


def _pack_payload(payload: QQBindingTokenPayload) -> bytes:
    try:
        steamid64 = int(payload.steamid64)
    except ValueError as exc:
        raise ValueError("steamid64 must be numeric") from exc
    if steamid64 < _QQ_BIND_TOKEN_STEAMID64_BASE:
        raise ValueError("steamid64 is out of range")
    steam_account_id = steamid64 - _QQ_BIND_TOKEN_STEAMID64_BASE
    if steam_account_id < 0 or steam_account_id >= 1 << 32:
        raise ValueError("steamid64 is out of range")
    if payload.exp < 0 or payload.exp >= 1 << 32:
        raise ValueError("exp is out of range")

    return b"".join(
        (
            steam_account_id.to_bytes(4, "big"),
            payload.exp.to_bytes(4, "big"),
        )
    )


def _unpack_payload(value: bytes) -> QQBindingTokenPayload:
    if len(value) != _QQ_BIND_TOKEN_PAYLOAD_LENGTH:
        raise ValueError("Invalid QQ binding code payload length")

    steam_account_id = int.from_bytes(value[0:4], "big")
    exp = int.from_bytes(value[4:8], "big")
    steamid64 = str(_QQ_BIND_TOKEN_STEAMID64_BASE + steam_account_id)
    return QQBindingTokenPayload(
        steamid64=steamid64,
        exp=exp,
    )


def _base62_encode(value: bytes) -> str:
    number = int.from_bytes(value, "big")
    digits: list[str] = []
    while number > 0:
        number, remainder = divmod(number, 62)
        digits.append(_BASE62_ALPHABET[remainder])

    encoded = "".join(reversed(digits)) or "0"
    return encoded.rjust(QQ_BIND_TOKEN_SUFFIX_LENGTH, "0")


def _base62_decode(
    value: str,
    *,
    encoded_length: int,
    decoded_length: int,
) -> bytes:
    if len(value) != encoded_length:
        raise ValueError("Invalid QQ binding code length")
    if any(character not in _BASE62_ALPHABET for character in value):
        raise ValueError("Invalid QQ binding code encoding")

    try:
        number = 0
        for character in value:
            number = (number * 62) + _BASE62_ALPHABET.index(character)
    except ValueError as exc:
        raise ValueError("Invalid QQ binding code encoding") from exc

    try:
        return number.to_bytes(decoded_length, "big")
    except OverflowError as exc:
        raise ValueError("Invalid QQ binding code encoding") from exc
