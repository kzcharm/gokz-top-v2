from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models import (
    KZMode,
    Map,
    Player,
    PlayerNotification,
    PlayerNotificationType,
    PlayerReport,
    Record,
    ServerGlobalapi,
    User,
    UserRole,
)
from tests.utils.utils import get_user_token_headers, random_steamid64

pytestmark = pytest.mark.asyncio


async def _create_player(
    *,
    db: AsyncSession,
    steamid64: int,
    name: str,
) -> Player:
    player = await db.get(Player, steamid64)
    if player is not None:
        player.name = name
        db.add(player)
        await db.commit()
        await db.refresh(player)
        return player

    player = Player(steamid64=steamid64, name=name)
    db.add(player)
    await db.commit()
    await db.refresh(player)
    return player


async def _create_user(
    *,
    db: AsyncSession,
    steamid64: int,
    name: str,
    roles: list[UserRole] | None = None,
    is_active: bool = True,
) -> User:
    await _create_player(db=db, steamid64=steamid64, name=name)
    user = await db.get(User, steamid64)
    if user is None:
        user = User(
            steamid64=steamid64,
            roles=roles or [],
            is_active=is_active,
        )
    else:
        user.roles = roles or []
        user.is_active = is_active
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _create_record(
    *,
    db: AsyncSession,
    record_steamid64: int,
    map_id: int,
) -> Record:
    owner = await db.get(Player, record_steamid64)
    if owner is None:
        await _create_player(
            db=db,
            steamid64=record_steamid64,
            name=f"Player {record_steamid64}",
        )

    map_obj = Map(
        id=map_id,
        name=f"kz_report_test_{map_id}",
        filesize=123456,
        validated=True,
        difficulty=3,
        approved_by_steamid64=record_steamid64,
    )
    server = ServerGlobalapi(
        id=map_id,
        port=27015,
        ip=f"203.0.113.{map_id % 255}",
        name=f"Report Test Server {map_id}",
        owner_steamid64=record_steamid64,
        approval_status=1,
        approved_by_steamid64=record_steamid64,
    )
    db.add(map_obj)
    db.add(server)
    await db.commit()

    record = Record(
        id=map_id,
        steamid64=record_steamid64,
        server_id=server.id,
        mode=KZMode.KZT,
        map_id=map_obj.id,
        stage=0,
        time=Decimal("12.345"),
        teleports=0,
        points=1000,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        updated_by=record_steamid64,
        is_valid=True,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def test_create_player_report_notifies_admins_and_root(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    reporter_steamid64 = random_steamid64()
    target_steamid64 = random_steamid64()
    admin_steamid64 = random_steamid64()
    inactive_admin_steamid64 = random_steamid64()
    await _create_user(db=db, steamid64=reporter_steamid64, name="Reporter")
    await _create_player(db=db, steamid64=target_steamid64, name="Target")
    await _create_user(
        db=db,
        steamid64=admin_steamid64,
        name="Admin",
        roles=[UserRole.ADMIN],
    )
    await _create_user(
        db=db,
        steamid64=settings.SUPER_USER_STEAMID64,
        name="Root",
        roles=[],
    )
    await _create_user(
        db=db,
        steamid64=inactive_admin_steamid64,
        name="Inactive Admin",
        roles=[UserRole.ADMIN],
        is_active=False,
    )
    headers = await get_user_token_headers(client, reporter_steamid64)

    response = await client.post(
        f"{settings.API_V1_STR}/player-reports",
        headers=headers,
        json={
            "target_steamid64": str(target_steamid64),
            "description": "This player is using a suspicious macro.",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["reporter_steamid64"] == str(reporter_steamid64)
    assert payload["target_steamid64"] == str(target_steamid64)
    assert payload["record_uuid"] is None
    assert payload["description"] == "This player is using a suspicious macro."

    reports = (
        await db.exec(
            select(PlayerReport).where(
                col(PlayerReport.target_steamid64) == target_steamid64
            )
        )
    ).all()
    assert len(reports) == 1

    notifications = (
        await db.exec(
            select(PlayerNotification).where(
                col(PlayerNotification.type) == PlayerNotificationType.PLAYER_REPORT
            )
        )
    ).all()
    assert {notification.recipient_steamid64 for notification in notifications} == {
        admin_steamid64,
        settings.SUPER_USER_STEAMID64,
    }
    assert all(
        notification.actor_steamid64 == reporter_steamid64
        and notification.target_player_steamid64 == target_steamid64
        and notification.comment_preview == "This player is using a suspicious macro."
        for notification in notifications
    )


async def test_create_player_report_includes_record_context(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    reporter_steamid64 = random_steamid64()
    target_steamid64 = random_steamid64()
    await _create_user(db=db, steamid64=reporter_steamid64, name="Reporter")
    await _create_user(
        db=db,
        steamid64=settings.SUPER_USER_STEAMID64,
        name="Root",
        roles=[UserRole.SUPERUSER],
    )
    record = await _create_record(
        db=db,
        record_steamid64=target_steamid64,
        map_id=912301,
    )
    headers = await get_user_token_headers(client, reporter_steamid64)

    response = await client.post(
        f"{settings.API_V1_STR}/player-reports",
        headers=headers,
        json={
            "target_steamid64": str(target_steamid64),
            "record_uuid": str(record.uuid),
            "description": "The linked record looks impossible.",
        },
    )

    assert response.status_code == 201
    assert response.json()["record_uuid"] == str(record.uuid)

    notification = (
        await db.exec(
            select(PlayerNotification).where(
                col(PlayerNotification.type) == PlayerNotificationType.PLAYER_REPORT
            )
        )
    ).one()
    assert notification.new_record_uuid == record.uuid
    assert notification.target_url == f"/profile/{target_steamid64}/records"


async def test_create_player_report_allows_own_record_context(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    reporter_steamid64 = random_steamid64()
    await _create_user(db=db, steamid64=reporter_steamid64, name="Reporter")
    await _create_user(
        db=db,
        steamid64=settings.SUPER_USER_STEAMID64,
        name="Root",
        roles=[UserRole.SUPERUSER],
    )
    record = await _create_record(
        db=db,
        record_steamid64=reporter_steamid64,
        map_id=912303,
    )
    headers = await get_user_token_headers(client, reporter_steamid64)

    response = await client.post(
        f"{settings.API_V1_STR}/player-reports",
        headers=headers,
        json={
            "target_steamid64": str(reporter_steamid64),
            "record_uuid": str(record.uuid),
            "description": "My linked record needs admin review.",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["reporter_steamid64"] == str(reporter_steamid64)
    assert payload["target_steamid64"] == str(reporter_steamid64)
    assert payload["record_uuid"] == str(record.uuid)

    notification = (
        await db.exec(
            select(PlayerNotification).where(
                col(PlayerNotification.type) == PlayerNotificationType.PLAYER_REPORT
            )
        )
    ).one()
    assert notification.actor_steamid64 == reporter_steamid64
    assert notification.target_player_steamid64 == reporter_steamid64
    assert notification.new_record_uuid == record.uuid


async def test_create_player_report_rejects_record_for_other_player(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    reporter_steamid64 = random_steamid64()
    target_steamid64 = random_steamid64()
    other_steamid64 = random_steamid64()
    await _create_user(db=db, steamid64=reporter_steamid64, name="Reporter")
    await _create_player(db=db, steamid64=target_steamid64, name="Target")
    record = await _create_record(
        db=db,
        record_steamid64=other_steamid64,
        map_id=912302,
    )
    headers = await get_user_token_headers(client, reporter_steamid64)

    response = await client.post(
        f"{settings.API_V1_STR}/player-reports",
        headers=headers,
        json={
            "target_steamid64": str(target_steamid64),
            "record_uuid": str(record.uuid),
            "description": "Wrong player record.",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Record does not belong to the reported player"


async def test_create_player_report_requires_auth(client: AsyncClient) -> None:
    response = await client.post(
        f"{settings.API_V1_STR}/player-reports",
        json={
            "target_steamid64": str(random_steamid64()),
            "description": "Missing auth.",
        },
    )

    assert response.status_code == 401
