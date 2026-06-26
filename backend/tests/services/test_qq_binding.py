from datetime import UTC, datetime, timedelta

import pytest

from app.services import qq_binding
from app.services.qq_binding import (
    QQ_BIND_TOKEN_PREFIX,
    QQ_BIND_TOKEN_SUFFIX_LENGTH,
)


def _mutate_code(
    *,
    code: str,
    mutate_payload: bool = False,
    mutate_signature: bool = False,
    resign_payload: bool = True,
) -> str:
    encoded_body = code.removeprefix(QQ_BIND_TOKEN_PREFIX)
    raw_bytes = qq_binding._base62_decode(
        encoded_body,
        encoded_length=QQ_BIND_TOKEN_SUFFIX_LENGTH,
        decoded_length=qq_binding._QQ_BIND_TOKEN_RAW_LENGTH,
    )
    payload_bytes = bytearray(raw_bytes[: qq_binding._QQ_BIND_TOKEN_PAYLOAD_LENGTH])
    signature_bytes = raw_bytes[qq_binding._QQ_BIND_TOKEN_PAYLOAD_LENGTH :]

    if mutate_payload:
        payload_bytes[3] ^= 0x01

    new_payload_bytes = bytes(payload_bytes)
    new_signature_bytes = (
        qq_binding._sign_payload(new_payload_bytes) if resign_payload else signature_bytes
    )

    if mutate_signature:
        mutated_signature = bytearray(new_signature_bytes)
        mutated_signature[-1] ^= 0x01
        new_signature_bytes = bytes(mutated_signature)

    return f"{QQ_BIND_TOKEN_PREFIX}{qq_binding._base62_encode(new_payload_bytes + new_signature_bytes)}"


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
    assert len(result.code) == len(QQ_BIND_TOKEN_PREFIX) + QQ_BIND_TOKEN_SUFFIX_LENGTH
    assert result.expires_at == now + timedelta(minutes=10)

    payload = qq_binding.verify_qq_binding_code(code=result.code, now=now)

    assert payload.steamid64 == "76561198000000001"
    assert payload.exp == int((now + timedelta(minutes=10)).timestamp())


def test_create_qq_binding_code_uses_fixed_length_base62_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(qq_binding.settings, "QQ_BIND_TOKEN_SECRET", "qq-secret")

    code = qq_binding.create_qq_binding_code(steamid64="76561198000000001").code
    suffix = code.removeprefix(QQ_BIND_TOKEN_PREFIX)

    assert len(code) == 27
    assert len(suffix) == QQ_BIND_TOKEN_SUFFIX_LENGTH
    assert suffix
    assert all(character.isalnum() for character in code)
    assert any(character.islower() for character in suffix)
    assert any(character.isupper() for character in suffix)


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


def test_verify_qq_binding_code_rejects_invalid_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(qq_binding.settings, "QQ_BIND_TOKEN_SECRET", "qq-secret")
    code = qq_binding.create_qq_binding_code(steamid64="76561198000000001").code

    with pytest.raises(ValueError, match="length"):
        qq_binding.verify_qq_binding_code(code=code[:-1])


def test_verify_qq_binding_code_rejects_invalid_encoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(qq_binding.settings, "QQ_BIND_TOKEN_SECRET", "qq-secret")
    code = qq_binding.create_qq_binding_code(steamid64="76561198000000001").code

    with pytest.raises(ValueError, match="encoding"):
        qq_binding.verify_qq_binding_code(code=f"{code[:-1]}_")


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


def test_create_qq_binding_code_rejects_non_numeric_steamid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(qq_binding.settings, "QQ_BIND_TOKEN_SECRET", "qq-secret")

    with pytest.raises(ValueError, match="numeric"):
        qq_binding.create_qq_binding_code(steamid64="abc")


def test_create_qq_binding_code_rejects_out_of_range_steamid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(qq_binding.settings, "QQ_BIND_TOKEN_SECRET", "qq-secret")

    with pytest.raises(ValueError, match="out of range"):
        qq_binding.create_qq_binding_code(
            steamid64=str(qq_binding._QQ_BIND_TOKEN_STEAMID64_BASE - 1)
        )


def test_create_qq_binding_code_rejects_steamid_above_uint32_account_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(qq_binding.settings, "QQ_BIND_TOKEN_SECRET", "qq-secret")
    too_large = qq_binding._QQ_BIND_TOKEN_STEAMID64_BASE + (1 << 32)

    with pytest.raises(ValueError, match="out of range"):
        qq_binding.create_qq_binding_code(steamid64=str(too_large))


def test_create_qq_binding_code_requires_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(qq_binding.settings, "QQ_BIND_TOKEN_SECRET", None)

    with pytest.raises(ValueError, match="not configured"):
        qq_binding.create_qq_binding_code(steamid64="76561198000000001")
