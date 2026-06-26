import hashlib
import hmac
import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.models import QQBindingCodePublic, QQBindingTokenPayload, generate_uuid7

QQ_BIND_TOKEN_PREFIX = "KZTOP"
QQ_BIND_TOKEN_SEPARATOR = "-"
QQ_BIND_TOKEN_ISSUER = "gokz-top"
QQ_BIND_TOKEN_AUDIENCE = "qq-bind"
QQ_BIND_TOKEN_VERSION = 1
QQ_BIND_TOKEN_EXPIRE_SECONDS = 600
_QQ_BIND_TOKEN_ISSUER_ID = 1
_QQ_BIND_TOKEN_AUDIENCE_ID = 1
_QQ_BIND_TOKEN_PAYLOAD_LENGTH = 35
_QQ_BIND_TOKEN_SIGNATURE_LENGTH = 16
_BASE36_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"


def ensure_qq_bind_token_configured() -> None:
    if not settings.QQ_BIND_TOKEN_SECRET:
        raise ValueError("QQ binding code generation is not configured")


def create_qq_binding_code(
    *,
    steamid64: int | str,
    now: datetime | None = None,
) -> QQBindingCodePublic:
    ensure_qq_bind_token_configured()

    issued_at = (now or datetime.now(UTC)).astimezone(UTC)
    expires_at = issued_at + timedelta(seconds=QQ_BIND_TOKEN_EXPIRE_SECONDS)
    payload = QQBindingTokenPayload(
        steamid64=str(steamid64),
        iss=QQ_BIND_TOKEN_ISSUER,
        aud=QQ_BIND_TOKEN_AUDIENCE,
        iat=int(issued_at.timestamp()),
        exp=int(expires_at.timestamp()),
        jti=str(generate_uuid7()),
        v=QQ_BIND_TOKEN_VERSION,
    )
    payload_bytes = _pack_payload(payload)
    signature_bytes = _sign_payload(payload_bytes)
    code = (
        f"{QQ_BIND_TOKEN_PREFIX}{_base36_encode(payload_bytes)}"
        f"{QQ_BIND_TOKEN_SEPARATOR}{_base36_encode(signature_bytes)}"
    )
    return QQBindingCodePublic(code=code, expires_at=expires_at)


def verify_qq_binding_code(
    *,
    code: str,
    now: datetime | None = None,
) -> QQBindingTokenPayload:
    ensure_qq_bind_token_configured()
    if not code.startswith(QQ_BIND_TOKEN_PREFIX):
        raise ValueError("Invalid QQ binding code prefix")

    encoded_body = code.removeprefix(QQ_BIND_TOKEN_PREFIX)
    if not encoded_body:
        raise ValueError("Invalid QQ binding code")

    payload_encoded, separator, signature_encoded = encoded_body.partition(
        QQ_BIND_TOKEN_SEPARATOR
    )
    if (
        separator != QQ_BIND_TOKEN_SEPARATOR
        or not payload_encoded
        or not signature_encoded
        or QQ_BIND_TOKEN_SEPARATOR in signature_encoded
    ):
        raise ValueError("Invalid QQ binding code format")

    payload_bytes = _base36_decode(
        payload_encoded,
        length=_QQ_BIND_TOKEN_PAYLOAD_LENGTH,
    )
    provided_signature_bytes = _base36_decode(
        signature_encoded,
        length=_QQ_BIND_TOKEN_SIGNATURE_LENGTH,
    )
    expected_signature_bytes = _sign_payload(payload_bytes)
    if not hmac.compare_digest(provided_signature_bytes, expected_signature_bytes):
        raise ValueError("Invalid QQ binding code signature")

    payload = _unpack_payload(payload_bytes)

    if payload.iss != QQ_BIND_TOKEN_ISSUER:
        raise ValueError("Invalid QQ binding code issuer")
    if payload.aud != QQ_BIND_TOKEN_AUDIENCE:
        raise ValueError("Invalid QQ binding code audience")
    if payload.v != QQ_BIND_TOKEN_VERSION:
        raise ValueError("Invalid QQ binding code version")

    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    if payload.exp < int(current_time.timestamp()):
        raise ValueError("QQ binding code has expired")

    return payload


def _sign_payload(payload_bytes: bytes) -> bytes:
    secret = settings.QQ_BIND_TOKEN_SECRET
    if not secret:
        raise ValueError("QQ binding code generation is not configured")
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
    if steamid64 < 0 or steamid64 >= 1 << 64:
        raise ValueError("steamid64 is out of range")
    if payload.iat < 0 or payload.iat >= 1 << 32:
        raise ValueError("iat is out of range")
    if payload.exp < 0 or payload.exp >= 1 << 32:
        raise ValueError("exp is out of range")

    try:
        jti_bytes = uuid.UUID(payload.jti).bytes
    except ValueError as exc:
        raise ValueError("jti must be a UUID") from exc

    return b"".join(
        (
            payload.v.to_bytes(1, "big"),
            _QQ_BIND_TOKEN_ISSUER_ID.to_bytes(1, "big"),
            _QQ_BIND_TOKEN_AUDIENCE_ID.to_bytes(1, "big"),
            steamid64.to_bytes(8, "big"),
            payload.iat.to_bytes(4, "big"),
            payload.exp.to_bytes(4, "big"),
            jti_bytes,
        )
    )


def _unpack_payload(value: bytes) -> QQBindingTokenPayload:
    if len(value) != _QQ_BIND_TOKEN_PAYLOAD_LENGTH:
        raise ValueError("Invalid QQ binding code payload length")

    version = value[0]
    issuer_id = value[1]
    audience_id = value[2]
    if issuer_id != _QQ_BIND_TOKEN_ISSUER_ID:
        raise ValueError("Invalid QQ binding code issuer")
    if audience_id != _QQ_BIND_TOKEN_AUDIENCE_ID:
        raise ValueError("Invalid QQ binding code audience")

    steamid64 = str(int.from_bytes(value[3:11], "big"))
    iat = int.from_bytes(value[11:15], "big")
    exp = int.from_bytes(value[15:19], "big")
    jti = str(uuid.UUID(bytes=value[19:35]))
    return QQBindingTokenPayload(
        steamid64=steamid64,
        iss=QQ_BIND_TOKEN_ISSUER,
        aud=QQ_BIND_TOKEN_AUDIENCE,
        iat=iat,
        exp=exp,
        jti=jti,
        v=version,
    )


def _base36_encode(value: bytes) -> str:
    number = int.from_bytes(value, "big")
    if number == 0:
        return "0"

    digits: list[str] = []
    while number > 0:
        number, remainder = divmod(number, 36)
        digits.append(_BASE36_ALPHABET[remainder])
    return "".join(reversed(digits))


def _base36_decode(value: str, *, length: int) -> bytes:
    if not value or any(character not in _BASE36_ALPHABET for character in value):
        raise ValueError("Invalid QQ binding code encoding")

    try:
        number = int(value, 36)
    except ValueError as exc:
        raise ValueError("Invalid QQ binding code encoding") from exc

    try:
        return number.to_bytes(length, "big")
    except OverflowError as exc:
        raise ValueError("Invalid QQ binding code encoding") from exc
