from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import QQBindingSecret


class QQBindingSecretAlreadyConfiguredError(ValueError):
    pass


async def get_qq_binding_secret(*, session: AsyncSession) -> QQBindingSecret | None:
    return await session.get(QQBindingSecret, 1)


async def create_qq_binding_secret(
    *, session: AsyncSession, encrypted_secret: str
) -> QQBindingSecret:
    secret = QQBindingSecret(encrypted_secret=encrypted_secret)
    session.add(secret)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise QQBindingSecretAlreadyConfiguredError(
            "QQ binding secret is already configured"
        ) from exc
    await session.refresh(secret)
    return secret


async def rotate_qq_binding_secret(
    *, session: AsyncSession, secret: QQBindingSecret, encrypted_secret: str
) -> QQBindingSecret:
    secret.encrypted_secret = encrypted_secret
    secret.updated_at = datetime.now(UTC)
    session.add(secret)
    await session.commit()
    await session.refresh(secret)
    return secret


async def delete_qq_binding_secret(
    *, session: AsyncSession, secret: QQBindingSecret
) -> None:
    await session.delete(secret)
    await session.commit()
