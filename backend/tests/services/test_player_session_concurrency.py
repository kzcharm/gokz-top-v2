"""Exercise overlapping session updates across real commit boundaries."""

import asyncio
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import Session
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import init_db
from app.crud import player_session as crud
from app.models import PlayerSession, PlayerSessionDisconnect, PlayerSessionHeartbeat
from tests.services.test_player_session_timeout import _connect_payload
from tests.utils.server import create_server_group


@pytest.mark.parametrize(
    "delayed_kind,delayed_seconds,first_kind,first_seconds,heartbeat,disconnect",
    [
        ("heartbeat", 10, "heartbeat", 20, 20, None),
        ("heartbeat", 30, "disconnect", 20, 20, 20),
        ("disconnect", 10, "heartbeat", 20, 20, 10),
        ("disconnect", 30, "disconnect", 20, 20, 20),
    ],
)
def test_overlapping_session_updates_preserve_committed_state(
    monkeypatch,
    delayed_kind,
    delayed_seconds,
    first_kind,
    first_seconds,
    heartbeat,
    disconnect,
):
    assert settings.ENVIRONMENT == "local"
    assert settings.POSTGRES_SERVER in {"localhost", "127.0.0.1"}
    name = f"sessions_{uuid.uuid4().hex}_test"
    url = make_url(str(settings.SQLALCHEMY_DATABASE_URI))
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            env={**os.environ, "POSTGRES_DB": name},
            check=True,
            capture_output=True,
        )
        sync_engine = create_engine(url.set(database=name))
        with Session(sync_engine) as session:
            init_db(session)
        sync_engine.dispose()

        async def exercise():
            engine = create_async_engine(url.set(database=name))
            connected = datetime(2026, 11, 6, tzinfo=UTC)
            try:
                async with AsyncSession(engine, expire_on_commit=False) as setup:
                    group, _ = await create_server_group(setup)
                    row = await crud.connect_player_session(
                        session=setup,
                        group=group,
                        payload=_connect_payload(connected_at=connected),
                    )
                    session_id = row.id

                async with (
                    AsyncSession(engine, expire_on_commit=False) as delayed,
                    AsyncSession(engine, expire_on_commit=False) as first,
                ):
                    loaded = asyncio.Event()
                    resume = asyncio.Event()
                    original = crud.get_player_session_by_id

                    async def pause_after_read(*, session, session_id):
                        result = await original(session=session, session_id=session_id)
                        if session is delayed:
                            loaded.set()
                            await resume.wait()
                        return result

                    monkeypatch.setattr(
                        crud, "get_player_session_by_id", pause_after_read
                    )

                    async def apply(session, kind, seconds):
                        timestamp = connected + timedelta(seconds=seconds)
                        if kind == "heartbeat":
                            return await crud.heartbeat_player_session(
                                session=session,
                                group=group,
                                payload=PlayerSessionHeartbeat(
                                    session_id=session_id, heartbeat_at=timestamp
                                ),
                            )
                        return await crud.disconnect_player_session(
                            session=session,
                            group=group,
                            payload=PlayerSessionDisconnect(
                                session_id=session_id, disconnect_at=timestamp
                            ),
                        )

                    request = asyncio.create_task(
                        apply(delayed, delayed_kind, delayed_seconds)
                    )
                    try:
                        await asyncio.wait_for(loaded.wait(), timeout=3)
                        await asyncio.wait_for(
                            apply(first, first_kind, first_seconds), timeout=3
                        )
                        resume.set()
                        response = await asyncio.wait_for(request, timeout=3)
                    finally:
                        if not request.done():
                            request.cancel()
                            await asyncio.gather(request, return_exceptions=True)

                async with AsyncSession(engine) as check:
                    persisted = await check.get(PlayerSession, session_id)
                    for result in (response, persisted):
                        assert result.last_heartbeat_at == connected + timedelta(
                            seconds=heartbeat
                        )
                        assert result.disconnect_at == (
                            connected + timedelta(seconds=disconnect)
                            if disconnect is not None
                            else None
                        )
                        assert result.duration_seconds == disconnect
            finally:
                await engine.dispose()

        asyncio.run(asyncio.wait_for(exercise(), timeout=30))
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()
