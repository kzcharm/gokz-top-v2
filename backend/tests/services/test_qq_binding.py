from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.services import qq_binding
from app.services.qq_binding import QQ_BIND_TOKEN_PREFIX, QQ_BIND_TOKEN_SUFFIX_LENGTH


async def _configure_secret(session: AsyncSession, secret: str = "qq-secret") -> str:
    await crud.create_qq_binding_secret(
        session=session,
        encrypted_secret=qq_binding.encrypt_qq_binding_secret(secret),
    )
    return secret


def _mutate_code(
    *,
    code: str,
    secret: str,
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
        qq_binding._sign_payload(new_payload_bytes, secret=secret)
        if resign_payload
        else signature_bytes
    )
    if mutate_signature:
        mutated_signature = bytearray(new_signature_bytes)
        mutated_signature[-1] ^= 0x01
        new_signature_bytes = bytes(mutated_signature)
    return f"{QQ_BIND_TOKEN_PREFIX}{qq_binding._base62_encode(new_payload_bytes + new_signature_bytes)}"


@pytest.mark.asyncio
async def test_create_and_verify_qq_binding_code_round_trip(db: AsyncSession) -> None:
    await _configure_secret(db)
    now = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)
    result = await qq_binding.create_qq_binding_code(
        session=db, steamid64="76561198000000001", now=now
    )
    assert result.code.startswith(QQ_BIND_TOKEN_PREFIX)
    assert len(result.code) == len(QQ_BIND_TOKEN_PREFIX) + QQ_BIND_TOKEN_SUFFIX_LENGTH
    assert result.expires_at == now + timedelta(minutes=10)
    payload = await qq_binding.verify_qq_binding_code(
        session=db, code=result.code, now=now
    )
    assert payload.steamid64 == "76561198000000001"


@pytest.mark.asyncio
async def test_qq_binding_secret_is_encrypted_at_rest(db: AsyncSession) -> None:
    raw_secret = await _configure_secret(db, "sensitive-qq-secret")
    stored_secret = await crud.get_qq_binding_secret(session=db)
    assert stored_secret is not None
    assert stored_secret.encrypted_secret != raw_secret
    assert qq_binding.decrypt_qq_binding_secret(stored_secret.encrypted_secret) == raw_secret


@pytest.mark.asyncio
async def test_verify_qq_binding_code_rejects_modified_code(db: AsyncSession) -> None:
    secret = await _configure_secret(db)
    code = (
        await qq_binding.create_qq_binding_code(
            session=db, steamid64="76561198000000001"
        )
    ).code
    with pytest.raises(ValueError, match="signature"):
        await qq_binding.verify_qq_binding_code(
            session=db,
            code=_mutate_code(
                code=code,
                secret=secret,
                mutate_payload=True,
                resign_payload=False,
            ),
        )
    with pytest.raises(ValueError, match="signature"):
        await qq_binding.verify_qq_binding_code(
            session=db,
            code=_mutate_code(code=code, secret=secret, mutate_signature=True),
        )


@pytest.mark.asyncio
async def test_verify_qq_binding_code_rejects_invalid_or_expired_code(
    db: AsyncSession,
) -> None:
    await _configure_secret(db)
    now = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)
    code = (
        await qq_binding.create_qq_binding_code(
            session=db, steamid64="76561198000000001", now=now
        )
    ).code
    with pytest.raises(ValueError, match="prefix"):
        await qq_binding.verify_qq_binding_code(session=db, code=f"WRONG{code}")
    with pytest.raises(ValueError, match="length"):
        await qq_binding.verify_qq_binding_code(session=db, code=code[:-1])
    with pytest.raises(ValueError, match="encoding"):
        await qq_binding.verify_qq_binding_code(session=db, code=f"{code[:-1]}_")
    with pytest.raises(ValueError, match="expired"):
        await qq_binding.verify_qq_binding_code(
            session=db, code=code, now=now + timedelta(minutes=10, seconds=1)
        )


@pytest.mark.asyncio
async def test_qq_binding_code_requires_active_secret(db: AsyncSession) -> None:
    with pytest.raises(ValueError, match="not configured"):
        await qq_binding.create_qq_binding_code(
            session=db, steamid64="76561198000000001"
        )
