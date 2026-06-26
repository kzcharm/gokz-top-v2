from datetime import UTC, datetime, timedelta

import pytest

from app.services import qq_binding
from app.services.qq_binding import (
    QQ_BIND_TOKEN_AUDIENCE,
    QQ_BIND_TOKEN_ISSUER,
    QQ_BIND_TOKEN_PREFIX,
    QQ_BIND_TOKEN_SEPARATOR,
    QQ_BIND_TOKEN_VERSION,
)


def _mutate_code(
    *,
    code: str,
    mutate_payload: bool = False,
    mutate_signature: bool = False,
    resign_payload: bool = True,
    issuer_id: int | None = None,
    audience_id: int | None = None,
    version: int | None = None,
) -> str:
    encoded_body = code.removeprefix(QQ_BIND_TOKEN_PREFIX)
    payload_encoded, _, signature_encoded = encoded_body.partition(
        QQ_BIND_TOKEN_SEPARATOR
    )

    payload_bytes = bytearray(
        qq_binding._base36_decode(
            payload_encoded,
            length=qq_binding._QQ_BIND_TOKEN_PAYLOAD_LENGTH,
        )
    )
    signature_bytes = qq_binding._base36_decode(
        signature_encoded,
        length=qq_binding._QQ_BIND_TOKEN_SIGNATURE_LENGTH,
    )

    if version is not None:
        payload_bytes[0] = version
    if issuer_id is not None:
        payload_bytes[1] = issuer_id
    if audience_id is not None:
        payload_bytes[2] = audience_id
    if mutate_payload:
        payload_bytes[10] ^= 0x01

    new_payload_bytes = bytes(payload_bytes)
    new_signature_bytes = (
        qq_binding._sign_payload(new_payload_bytes) if resign_payload else signature_bytes
    )

    if mutate_signature:
        mutated_signature = bytearray(new_signature_bytes)
        mutated_signature[-1] ^= 0x01
        new_signature_bytes = bytes(mutated_signature)

    return (
        f"{QQ_BIND_TOKEN_PREFIX}{qq_binding._base36_encode(new_payload_bytes)}"
        f"{QQ_BIND_TOKEN_SEPARATOR}{qq_binding._base36_encode(new_signature_bytes)}"
    )


def test_create_and_verify_qq_binding_code_round_trip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(qq_binding.settings, "QQ_BIND_TOKEN_SECRET", "qq-secret")
    now = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)

    result = qq_binding.create_qq_binding_code(
        steamid64="76561198000000001",
        now=now,
    )

    assert result.code.startswith(QQ_BIND_TOKEN_PREFIX)
    assert QQ_BIND_TOKEN_SEPARATOR in result.code
    assert "_" not in result.code
    assert result.expires_at == now + timedelta(minutes=10)

    payload = qq_binding.verify_qq_binding_code(code=result.code, now=now)

    assert payload.steamid64 == "76561198000000001"
    assert payload.iss == QQ_BIND_TOKEN_ISSUER
    assert payload.aud == QQ_BIND_TOKEN_AUDIENCE
    assert payload.v == QQ_BIND_TOKEN_VERSION


def test_create_qq_binding_code_uses_compact_lowercase_base36_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(qq_binding.settings, "QQ_BIND_TOKEN_SECRET", "qq-secret")

    code = qq_binding.create_qq_binding_code(steamid64="76561198000000001").code
    encoded_body = code.removeprefix(QQ_BIND_TOKEN_PREFIX)
    payload_encoded, separator, signature_encoded = encoded_body.partition(
        QQ_BIND_TOKEN_SEPARATOR
    )

    assert separator == QQ_BIND_TOKEN_SEPARATOR
    assert payload_encoded
    assert signature_encoded
    assert payload_encoded == payload_encoded.lower()
    assert signature_encoded == signature_encoded.lower()


def test_verify_qq_binding_code_rejects_modified_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(qq_binding.settings, "QQ_BIND_TOKEN_SECRET", "qq-secret")
    code = qq_binding.create_qq_binding_code(steamid64="76561198000000001").code

    with pytest.raises(ValueError, match="signature"):
        qq_binding.verify_qq_binding_code(
            code=_mutate_code(
                code=code,
                mutate_payload=True,
                resign_payload=False,
            )
        )


def test_verify_qq_binding_code_rejects_modified_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(qq_binding.settings, "QQ_BIND_TOKEN_SECRET", "qq-secret")
    code = qq_binding.create_qq_binding_code(steamid64="76561198000000001").code

    with pytest.raises(ValueError, match="signature"):
        qq_binding.verify_qq_binding_code(
            code=_mutate_code(code=code, mutate_signature=True)
        )


def test_verify_qq_binding_code_rejects_invalid_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(qq_binding.settings, "QQ_BIND_TOKEN_SECRET", "qq-secret")
    code = qq_binding.create_qq_binding_code(steamid64="76561198000000001").code

    with pytest.raises(ValueError, match="prefix"):
        qq_binding.verify_qq_binding_code(code=f"WRONG{code}")


def test_verify_qq_binding_code_rejects_missing_separator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(qq_binding.settings, "QQ_BIND_TOKEN_SECRET", "qq-secret")
    code = qq_binding.create_qq_binding_code(steamid64="76561198000000001").code

    with pytest.raises(ValueError, match="format"):
        qq_binding.verify_qq_binding_code(
            code=code.replace(QQ_BIND_TOKEN_SEPARATOR, "", 1)
        )


def test_verify_qq_binding_code_rejects_extra_separator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(qq_binding.settings, "QQ_BIND_TOKEN_SECRET", "qq-secret")
    code = qq_binding.create_qq_binding_code(steamid64="76561198000000001").code

    with pytest.raises(ValueError, match="format"):
        qq_binding.verify_qq_binding_code(code=f"{code}{QQ_BIND_TOKEN_SEPARATOR}a")


def test_verify_qq_binding_code_rejects_expired_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(qq_binding.settings, "QQ_BIND_TOKEN_SECRET", "qq-secret")
    now = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)
    code = qq_binding.create_qq_binding_code(
        steamid64="76561198000000001",
        now=now,
    ).code

    with pytest.raises(ValueError, match="expired"):
        qq_binding.verify_qq_binding_code(
            code=code,
            now=now + timedelta(minutes=10, seconds=1),
        )


def test_verify_qq_binding_code_rejects_wrong_issuer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(qq_binding.settings, "QQ_BIND_TOKEN_SECRET", "qq-secret")
    code = qq_binding.create_qq_binding_code(steamid64="76561198000000001").code

    with pytest.raises(ValueError, match="issuer"):
        qq_binding.verify_qq_binding_code(
            code=_mutate_code(code=code, issuer_id=2)
        )


def test_verify_qq_binding_code_rejects_wrong_audience(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(qq_binding.settings, "QQ_BIND_TOKEN_SECRET", "qq-secret")
    code = qq_binding.create_qq_binding_code(steamid64="76561198000000001").code

    with pytest.raises(ValueError, match="audience"):
        qq_binding.verify_qq_binding_code(
            code=_mutate_code(code=code, audience_id=2)
        )


def test_verify_qq_binding_code_rejects_wrong_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(qq_binding.settings, "QQ_BIND_TOKEN_SECRET", "qq-secret")
    code = qq_binding.create_qq_binding_code(steamid64="76561198000000001").code

    with pytest.raises(ValueError, match="version"):
        qq_binding.verify_qq_binding_code(code=_mutate_code(code=code, version=2))


def test_create_qq_binding_code_requires_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(qq_binding.settings, "QQ_BIND_TOKEN_SECRET", None)

    with pytest.raises(ValueError, match="not configured"):
        qq_binding.create_qq_binding_code(steamid64="76561198000000001")
