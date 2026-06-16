import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app import crud
from app.api.deps import CurrentUser, SessionDep
from app.models import (
    Message,
    PlayerNotificationListQuery,
    PlayerNotificationPublic,
    PlayerNotificationsPublic,
    PlayerNotificationUnreadCountPublic,
)

router = APIRouter(prefix="/me/notifications", tags=["me"])


@router.get("", response_model=PlayerNotificationsPublic)
async def read_current_player_notifications(
    session: SessionDep,
    current_user: CurrentUser,
    query: Annotated[PlayerNotificationListQuery, Query()],
) -> PlayerNotificationsPublic:
    rows, count = await crud.read_player_notifications(
        session=session,
        recipient_steamid64=current_user.steamid64,
        offset=query.offset,
        limit=query.limit,
        unread_only=query.unread_only,
    )
    return PlayerNotificationsPublic(
        data=[
            crud.to_player_notification_public(
                notification=notification,
                actor=actor,
                target_player=target_player,
            )
            for notification, actor, target_player in rows
        ],
        count=count,
    )


@router.get("/unread-count", response_model=PlayerNotificationUnreadCountPublic)
async def read_current_player_notification_unread_count(
    session: SessionDep,
    current_user: CurrentUser,
) -> PlayerNotificationUnreadCountPublic:
    unread_count = await crud.count_unread_player_notifications(
        session=session,
        recipient_steamid64=current_user.steamid64,
    )
    return PlayerNotificationUnreadCountPublic(unread_count=unread_count)


@router.patch("/{notification_id}/read", response_model=PlayerNotificationPublic)
async def mark_current_player_notification_read(
    notification_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> PlayerNotificationPublic:
    notification = await crud.mark_player_notification_read(
        session=session,
        notification_id=notification_id,
        recipient_steamid64=current_user.steamid64,
        read_at=datetime.now(UTC),
    )
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")

    actor = (
        await crud.get_player_by_steamid64(
            session=session,
            steamid64=notification.actor_steamid64,
        )
        if notification.actor_steamid64 is not None
        else None
    )
    target_player = (
        await crud.get_player_by_steamid64(
            session=session,
            steamid64=notification.target_player_steamid64,
        )
        if notification.target_player_steamid64 is not None
        else None
    )
    return crud.to_player_notification_public(
        notification=notification,
        actor=actor,
        target_player=target_player,
    )


@router.patch("/read-all", response_model=Message)
async def mark_all_current_player_notifications_read(
    session: SessionDep,
    current_user: CurrentUser,
) -> Message:
    updated_count = await crud.mark_all_player_notifications_read(
        session=session,
        recipient_steamid64=current_user.steamid64,
        read_at=datetime.now(UTC),
    )
    return Message(message=f"Marked {updated_count} notification(s) read")
