from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.models import (
    PlayerSessionConnect,
    PlayerSessionDisconnect,
    PlayerSessionHeartbeat,
    generate_uuid7,
)
from app.services import player_session_timeout
from tests.utils.server import create_server_group
from tests.utils.utils import random_steamid64

pytestmark = pytest.mark.asyncio


def _connect_payload(
    *,
    connected_at: datetime,
) -> PlayerSessionConnect:
    return PlayerSessionConnect(
        session_id=generate_uuid7(timestamp=connected_at),
        player_steamid64=str(random_steamid64()),
        connected_at=connected_at,
        ip_address="127.0.0.12",
        map_name="kz_timeout",
    )


async def test_close_timed_out_player_sessions_closes_only_stale_open_sessions(
    db: AsyncSession,
) -> None:
    group, _ = await create_server_group(db)
    now = datetime(2026, 4, 28, 12, 2, tzinfo=UTC)
    stale_connected_at = now - timedelta(seconds=120)
    fresh_connected_at = now - timedelta(seconds=30)

    stale = await crud.connect_player_session(
        session=db,
        group=group,
        payload=_connect_payload(connected_at=stale_connected_at),
    )
    fresh = await crud.connect_player_session(
        session=db,
        group=group,
        payload=_connect_payload(connected_at=fresh_connected_at),
    )
    stale.last_heartbeat_at = now - timedelta(seconds=61)
    db.add(stale)
    await db.commit()

    closed_count = await crud.close_timed_out_player_sessions(
        session=db,
        now=now,
        timeout=timedelta(seconds=60),
    )

    refreshed_stale = await crud.get_player_session_by_id(
        session=db,
        session_id=stale.id,
    )
    refreshed_fresh = await crud.get_player_session_by_id(
        session=db,
        session_id=fresh.id,
    )
    assert closed_count == 1
    assert refreshed_stale is not None
    assert refreshed_stale.disconnect_at == stale.last_heartbeat_at
    assert refreshed_fresh is not None
    assert refreshed_fresh.disconnect_at is None


async def test_closed_sessions_ignore_late_heartbeat_and_disconnect_retry(
    db: AsyncSession,
) -> None:
    group, _ = await create_server_group(db)
    connected_at = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
    disconnected_at = connected_at + timedelta(seconds=45)
    player_session = await crud.connect_player_session(
        session=db,
        group=group,
        payload=_connect_payload(connected_at=connected_at),
    )
    closed = await crud.disconnect_player_session(
        session=db,
        group=group,
        payload=PlayerSessionDisconnect(
            session_id=player_session.id,
            disconnect_at=disconnected_at,
        ),
    )
    assert closed is not None

    after_heartbeat = await crud.heartbeat_player_session(
        session=db,
        group=group,
        payload=PlayerSessionHeartbeat(
            session_id=player_session.id,
            heartbeat_at=disconnected_at + timedelta(seconds=30),
        ),
    )
    after_disconnect_retry = await crud.disconnect_player_session(
        session=db,
        group=group,
        payload=PlayerSessionDisconnect(
            session_id=player_session.id,
            disconnect_at=disconnected_at + timedelta(seconds=60),
        ),
    )

    assert after_heartbeat is not None
    assert after_heartbeat.disconnect_at == disconnected_at
    assert after_disconnect_retry is not None
    assert after_disconnect_retry.disconnect_at == disconnected_at


async def test_close_timed_out_player_sessions_once_uses_configured_timeout(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SessionContext:
        async def __aenter__(self) -> AsyncSession:
            return db

        async def __aexit__(self, *args: object) -> None:
            return None

    group, _ = await create_server_group(db)
    now = datetime(2026, 4, 28, 12, 2, tzinfo=UTC)
    player_session = await crud.connect_player_session(
        session=db,
        group=group,
        payload=_connect_payload(connected_at=now - timedelta(seconds=120)),
    )
    player_session.last_heartbeat_at = now - timedelta(seconds=61)
    db.add(player_session)
    await db.commit()

    monkeypatch.setattr(player_session_timeout, "get_datetime_utc", lambda: now)
    monkeypatch.setattr(
        player_session_timeout,
        "async_session_maker",
        lambda: SessionContext(),
    )
    monkeypatch.setattr(
        player_session_timeout.settings,
        "PLAYER_SESSION_TIMEOUT_SECONDS",
        60,
    )

    closed_count = await player_session_timeout.close_timed_out_player_sessions_once()
    refreshed = await crud.get_player_session_by_id(
        session=db,
        session_id=player_session.id,
    )

    assert closed_count == 1
    assert refreshed is not None
    assert refreshed.disconnect_at == player_session.last_heartbeat_at
