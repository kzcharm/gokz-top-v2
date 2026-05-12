import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import (
    PlayerWebhook,
    PlayerWebhookProvider,
    PlayerWebhookPublic,
    normalize_discord_webhook_url,
)


class PlayerWebhookConflictError(ValueError):
    pass


async def get_player_webhook(
    *, session: AsyncSession, id: uuid.UUID
) -> PlayerWebhook | None:
    return await session.get(PlayerWebhook, id)


async def list_player_webhooks(
    *, session: AsyncSession, user_steamid64: int
) -> list[PlayerWebhook]:
    statement = (
        select(PlayerWebhook)
        .where(col(PlayerWebhook.user_steamid64) == user_steamid64)
        .order_by(
            col(PlayerWebhook.created_at).asc(),
            col(PlayerWebhook.id).asc(),
        )
    )
    return list((await session.exec(statement)).all())


async def list_enabled_player_webhooks(
    *, session: AsyncSession, user_steamid64: int
) -> list[PlayerWebhook]:
    statement = (
        select(PlayerWebhook)
        .where(
            col(PlayerWebhook.user_steamid64) == user_steamid64,
            col(PlayerWebhook.enabled).is_(True),
        )
        .order_by(
            col(PlayerWebhook.created_at).asc(),
            col(PlayerWebhook.id).asc(),
        )
    )
    return list((await session.exec(statement)).all())


async def list_all_enabled_player_webhooks(
    *,
    session: AsyncSession,
) -> list[PlayerWebhook]:
    statement = (
        select(PlayerWebhook)
        .where(col(PlayerWebhook.enabled).is_(True))
        .order_by(
            col(PlayerWebhook.created_at).asc(),
            col(PlayerWebhook.id).asc(),
        )
    )
    return list((await session.exec(statement)).all())


async def create_player_webhook(
    *,
    session: AsyncSession,
    user_steamid64: int,
    url: str,
) -> PlayerWebhook:
    webhook = PlayerWebhook(
        user_steamid64=user_steamid64,
        provider=PlayerWebhookProvider.DISCORD,
        url=normalize_discord_webhook_url(url),
    )
    session.add(webhook)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise PlayerWebhookConflictError("Webhook already exists for this user") from exc

    await session.refresh(webhook)
    return webhook


async def update_player_webhook(
    *,
    session: AsyncSession,
    webhook: PlayerWebhook,
    url: str | None = None,
    enabled: bool | None = None,
) -> PlayerWebhook:
    if url is not None:
        webhook.url = normalize_discord_webhook_url(url)
    if enabled is not None:
        webhook.enabled = enabled

    webhook.updated_at = datetime.now(UTC)
    session.add(webhook)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise PlayerWebhookConflictError("Webhook already exists for this user") from exc

    await session.refresh(webhook)
    return webhook


async def mark_player_webhook_used(
    *,
    session: AsyncSession,
    webhook: PlayerWebhook,
    used_at: datetime,
) -> PlayerWebhook:
    webhook.last_used_at = used_at
    webhook.updated_at = used_at
    session.add(webhook)
    await session.commit()
    await session.refresh(webhook)
    return webhook


async def delete_player_webhook(
    *, session: AsyncSession, webhook: PlayerWebhook
) -> None:
    await session.delete(webhook)
    await session.commit()


def to_player_webhook_public(*, webhook: PlayerWebhook) -> PlayerWebhookPublic:
    return PlayerWebhookPublic(
        id=webhook.id,
        provider=webhook.provider,
        url=webhook.url,
        enabled=webhook.enabled,
        last_used_at=webhook.last_used_at,
        created_at=webhook.created_at,
        updated_at=webhook.updated_at,
    )


def to_player_webhook_publics(
    *, webhooks: Sequence[PlayerWebhook]
) -> list[PlayerWebhookPublic]:
    return [to_player_webhook_public(webhook=webhook) for webhook in webhooks]
