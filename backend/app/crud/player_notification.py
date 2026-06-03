import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import aliased
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.crud.player import to_player_ref_public
from app.models import (
    ModeScope,
    Player,
    PlayerNotification,
    PlayerNotificationPublic,
    PlayerNotificationType,
    RecordType,
)
from app.models.utils import get_datetime_utc

COMMENT_PREVIEW_LENGTH = 140
WR_NOTIFICATION_SCOPES = {ModeScope.KZT, ModeScope.SKZ, ModeScope.VNL}


def _profile_url(steamid64: int) -> str:
    return f"/profile/{steamid64}"


def _map_top_url(map_name: str, *, scope: ModeScope, record_type: RecordType) -> str:
    return f"/maps/{map_name}/maptop?scope={scope.value}&type={record_type.value}"


def _preview_text(text: str) -> str:
    normalized = " ".join(text.strip().split())
    return normalized[:COMMENT_PREVIEW_LENGTH]


def to_player_notification_public(
    *,
    notification: PlayerNotification,
    actor: Player | None,
) -> PlayerNotificationPublic:
    return PlayerNotificationPublic(
        id=notification.id,
        type=notification.type,
        created_at=notification.created_at,
        read_at=notification.read_at,
        actor=to_player_ref_public(player=actor) if actor is not None else None,
        target_url=notification.target_url,
        target_player_steamid64=(
            str(notification.target_player_steamid64)
            if notification.target_player_steamid64 is not None
            else None
        ),
        comment_id=notification.comment_id,
        comment_preview=notification.comment_preview,
        map_id=notification.map_id,
        map_name=notification.map_name,
        scope=notification.scope,
        record_type=notification.record_type,
        previous_record_uuid=notification.previous_record_uuid,
        new_record_uuid=notification.new_record_uuid,
        new_record_time=notification.new_record_time,
    )


async def create_player_notification(
    *,
    session: AsyncSession,
    recipient_steamid64: int,
    type: PlayerNotificationType,
    source_key: str,
    target_url: str,
    actor_steamid64: int | None = None,
    target_player_steamid64: int | None = None,
    comment_id: uuid.UUID | None = None,
    comment_preview: str | None = None,
    map_id: int | None = None,
    map_name: str | None = None,
    scope: ModeScope | None = None,
    record_type: RecordType | None = None,
    previous_record_uuid: uuid.UUID | None = None,
    new_record_uuid: uuid.UUID | None = None,
    new_record_time: Decimal | float | None = None,
    commit: bool = True,
) -> bool:
    values = {
        "recipient_steamid64": recipient_steamid64,
        "actor_steamid64": actor_steamid64,
        "type": type,
        "source_key": source_key,
        "target_url": target_url,
        "target_player_steamid64": target_player_steamid64,
        "comment_id": comment_id,
        "comment_preview": comment_preview,
        "map_id": map_id,
        "map_name": map_name,
        "scope": scope,
        "record_type": record_type,
        "previous_record_uuid": previous_record_uuid,
        "new_record_uuid": new_record_uuid,
        "new_record_time": float(new_record_time) if new_record_time is not None else None,
        "created_at": get_datetime_utc(),
    }
    statement = (
        insert(PlayerNotification)
        .values(**values)
        .on_conflict_do_nothing(index_elements=[PlayerNotification.source_key])
        .returning(PlayerNotification.id)
    )
    created_id = (await session.exec(statement)).one_or_none()
    if commit:
        await session.commit()
    else:
        await session.flush()
    return created_id is not None


async def create_profile_like_notification(
    *,
    session: AsyncSession,
    actor_steamid64: int,
    recipient_steamid64: int,
    like_date: str,
) -> bool:
    if actor_steamid64 == recipient_steamid64:
        return False
    return await create_player_notification(
        session=session,
        recipient_steamid64=recipient_steamid64,
        actor_steamid64=actor_steamid64,
        type=PlayerNotificationType.PROFILE_LIKE,
        source_key=(
            f"profile-like:{actor_steamid64}:{recipient_steamid64}:{like_date}"
        ),
        target_url=_profile_url(actor_steamid64),
        target_player_steamid64=actor_steamid64,
    )


async def create_profile_comment_notification(
    *,
    session: AsyncSession,
    actor_steamid64: int,
    recipient_steamid64: int,
    comment_id: uuid.UUID,
    text: str,
) -> bool:
    if actor_steamid64 == recipient_steamid64:
        return False
    return await create_player_notification(
        session=session,
        recipient_steamid64=recipient_steamid64,
        actor_steamid64=actor_steamid64,
        type=PlayerNotificationType.PROFILE_COMMENT,
        source_key=f"profile-comment:{comment_id}",
        target_url=f"{_profile_url(recipient_steamid64)}/comments",
        target_player_steamid64=recipient_steamid64,
        comment_id=comment_id,
        comment_preview=_preview_text(text),
    )


async def create_player_follow_notification(
    *,
    session: AsyncSession,
    actor_steamid64: int,
    recipient_steamid64: int,
) -> bool:
    if actor_steamid64 == recipient_steamid64:
        return False
    return await create_player_notification(
        session=session,
        recipient_steamid64=recipient_steamid64,
        actor_steamid64=actor_steamid64,
        type=PlayerNotificationType.PLAYER_FOLLOW,
        source_key=f"player-follow:{actor_steamid64}:{recipient_steamid64}",
        target_url=_profile_url(actor_steamid64),
        target_player_steamid64=actor_steamid64,
    )


async def create_wr_beaten_notification(
    *,
    session: AsyncSession,
    previous_owner_steamid64: int,
    new_owner_steamid64: int,
    map_id: int,
    map_name: str,
    scope: ModeScope,
    record_type: RecordType,
    previous_record_uuid: uuid.UUID,
    new_record_uuid: uuid.UUID,
    new_record_time: Decimal | float,
    commit: bool = True,
) -> bool:
    if scope not in WR_NOTIFICATION_SCOPES:
        return False
    if previous_owner_steamid64 == new_owner_steamid64:
        return False

    return await create_player_notification(
        session=session,
        recipient_steamid64=previous_owner_steamid64,
        actor_steamid64=new_owner_steamid64,
        type=PlayerNotificationType.WR_BEATEN,
        source_key=(
            "wr-beaten:"
            f"{scope.value}:{record_type.value}:{map_id}:"
            f"{previous_record_uuid}:{new_record_uuid}"
        ),
        target_url=_map_top_url(map_name, scope=scope, record_type=record_type),
        map_id=map_id,
        map_name=map_name,
        scope=scope,
        record_type=record_type,
        previous_record_uuid=previous_record_uuid,
        new_record_uuid=new_record_uuid,
        new_record_time=new_record_time,
        commit=commit,
    )


async def read_player_notifications(
    *,
    session: AsyncSession,
    recipient_steamid64: int,
    offset: int,
    limit: int,
    unread_only: bool,
) -> tuple[list[tuple[PlayerNotification, Player | None]], int]:
    filters = [col(PlayerNotification.recipient_steamid64) == recipient_steamid64]
    if unread_only:
        filters.append(col(PlayerNotification.read_at).is_(None))

    count_statement = select(func.count()).select_from(PlayerNotification).where(*filters)
    count = int((await session.exec(count_statement)).one())

    actor_player = aliased(Player)
    statement = (
        select(PlayerNotification, actor_player)
        .outerjoin(
            actor_player,
            col(actor_player.steamid64) == col(PlayerNotification.actor_steamid64),
        )
        .where(*filters)
        .order_by(
            col(PlayerNotification.created_at).desc(),
            col(PlayerNotification.id).desc(),
        )
        .offset(offset)
        .limit(limit)
    )
    return list((await session.exec(statement)).all()), count


async def count_unread_player_notifications(
    *,
    session: AsyncSession,
    recipient_steamid64: int,
) -> int:
    statement = select(func.count()).select_from(PlayerNotification).where(
        col(PlayerNotification.recipient_steamid64) == recipient_steamid64,
        col(PlayerNotification.read_at).is_(None),
    )
    return int((await session.exec(statement)).one())


async def mark_player_notification_read(
    *,
    session: AsyncSession,
    notification_id: uuid.UUID,
    recipient_steamid64: int,
    read_at: datetime,
) -> PlayerNotification | None:
    notification = await session.get(PlayerNotification, notification_id)
    if notification is None or notification.recipient_steamid64 != recipient_steamid64:
        return None

    if notification.read_at is None:
        notification.read_at = read_at
        session.add(notification)
        await session.commit()
        await session.refresh(notification)
    return notification


async def mark_all_player_notifications_read(
    *,
    session: AsyncSession,
    recipient_steamid64: int,
    read_at: datetime,
) -> int:
    statement = (
        update(PlayerNotification)
        .where(
            col(PlayerNotification.recipient_steamid64) == recipient_steamid64,
            col(PlayerNotification.read_at).is_(None),
        )
        .values(read_at=read_at)
    )
    result = await session.exec(statement)
    await session.commit()
    return int(result.rowcount or 0)
