import uuid
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, HTTPException

from app import crud
from app.api.deps import CurrentUser, SessionDep
from app.api.v1.player_api_helpers import (
    build_test_webhook_event,
    get_current_user_player_or_404,
    get_current_user_webhook_or_404,
)
from app.models import (
    PlayerWebhookCreate,
    PlayerWebhookPublic,
    PlayerWebhooksPublic,
    PlayerWebhookUpdate,
)
from app.services.player_webhooks import (
    build_discord_embed_payload,
    send_discord_webhook,
)

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/webhooks", response_model=PlayerWebhooksPublic)
async def read_current_player_webhooks(
    session: SessionDep,
    current_user: CurrentUser,
) -> PlayerWebhooksPublic:
    webhooks = await crud.list_player_webhooks(
        session=session,
        player_steamid64=current_user.steamid64,
    )
    return PlayerWebhooksPublic(
        data=crud.to_player_webhook_publics(webhooks=webhooks),
        count=len(webhooks),
    )


@router.post("/webhooks", response_model=PlayerWebhooksPublic)
async def create_current_player_webhook(
    session: SessionDep,
    current_user: CurrentUser,
    body: PlayerWebhookCreate,
) -> PlayerWebhooksPublic:
    try:
        await crud.create_player_webhook(
            session=session,
            player_steamid64=current_user.steamid64,
            url=body.url,
        )
    except crud.PlayerWebhookConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    webhooks = await crud.list_player_webhooks(
        session=session,
        player_steamid64=current_user.steamid64,
    )
    return PlayerWebhooksPublic(
        data=crud.to_player_webhook_publics(webhooks=webhooks),
        count=len(webhooks),
    )


@router.patch("/webhooks/{webhook_id}", response_model=PlayerWebhooksPublic)
async def update_current_player_webhook(
    webhook_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    body: PlayerWebhookUpdate,
) -> PlayerWebhooksPublic:
    webhook = await get_current_user_webhook_or_404(
        session=session,
        current_user=current_user,
        webhook_id=webhook_id,
    )
    try:
        await crud.update_player_webhook(
            session=session,
            webhook=webhook,
            url=body.url,
            enabled=body.enabled,
        )
    except crud.PlayerWebhookConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    webhooks = await crud.list_player_webhooks(
        session=session,
        player_steamid64=current_user.steamid64,
    )
    return PlayerWebhooksPublic(
        data=crud.to_player_webhook_publics(webhooks=webhooks),
        count=len(webhooks),
    )


@router.delete("/webhooks/{webhook_id}", response_model=PlayerWebhooksPublic)
async def delete_current_player_webhook(
    webhook_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> PlayerWebhooksPublic:
    webhook = await get_current_user_webhook_or_404(
        session=session,
        current_user=current_user,
        webhook_id=webhook_id,
    )
    await crud.delete_player_webhook(session=session, webhook=webhook)
    webhooks = await crud.list_player_webhooks(
        session=session,
        player_steamid64=current_user.steamid64,
    )
    return PlayerWebhooksPublic(
        data=crud.to_player_webhook_publics(webhooks=webhooks),
        count=len(webhooks),
    )


@router.post("/webhooks/{webhook_id}/test", response_model=PlayerWebhookPublic)
async def test_current_player_webhook(
    webhook_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> PlayerWebhookPublic:
    webhook = await get_current_user_webhook_or_404(
        session=session,
        current_user=current_user,
        webhook_id=webhook_id,
    )
    player = await get_current_user_player_or_404(
        session=session,
        current_user=current_user,
    )
    event = await build_test_webhook_event(session=session, player=player)
    payload = build_discord_embed_payload(event=event, is_test=True)
    try:
        await send_discord_webhook(webhook_url=webhook.url, payload=payload)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to send webhook: {exc}") from exc

    tested = await crud.mark_player_webhook_used(
        session=session,
        webhook=webhook,
        used_at=datetime.now(UTC),
    )
    return crud.to_player_webhook_public(webhook=tested)
