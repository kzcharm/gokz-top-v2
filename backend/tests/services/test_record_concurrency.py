"""Exercise real commit boundaries with independent PostgreSQL connections."""

import asyncio
import os
import subprocess
import sys
import uuid
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import create_engine, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import Session, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import init_db
from app.models import (
    KZMode,
    Player,
    Record,
    RecordUploadReceipt,
    ServerGlobalapi,
    ServerGroup,
)
from app.services.record_ingestion import accept_record
from tests.services.test_record_ingestion import setup_finish


def test_concurrent_receipts_and_conflicting_uuid():
    # Never touch an existing database: this test owns a randomly named database.
    assert settings.ENVIRONMENT == "local"
    assert settings.POSTGRES_SERVER in {"localhost", "127.0.0.1"}
    name = f"records_{uuid.uuid4().hex}_test"
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
            engine = create_async_engine(url.set(database=name), pool_size=12)
            try:
                async with AsyncSession(engine, expire_on_commit=False) as session:
                    group, _, payload = await setup_finish(session, KZMode.KZT)
                    session.add(
                        ServerGlobalapi(
                            id=998877,
                            name="shared endpoint",
                            ip="192.0.2.77",
                            port=27016,
                            group_id=group.id,
                        )
                    )
                    group_id = group.id
                    api_key = group.api_key
                    await session.commit()

                async def submit(key, finish):
                    async with AsyncSession(engine, expire_on_commit=False) as session:
                        group = await session.get(ServerGroup, group_id)
                        try:
                            return await accept_record(session, group, finish, key)
                        except HTTPException as exc:
                            await session.rollback()
                            return exc.status_code

                async def mirror():
                    from app.services.globalapi_record_sync import _upsert_record

                    async with AsyncSession(engine, expire_on_commit=False) as session:
                        result = await _upsert_record(
                            session=session,
                            payload={
                                "id": 998877,
                                "steamid64": payload.steamid64,
                                "server_id": 998877,
                                "map_id": 982345,
                                "mode": "kz_timer",
                                "stage": 0,
                                "time": "35.288",
                                "teleports": 0,
                                "created_on": payload.finished_at.isoformat(),
                                "updated_on": payload.finished_at.isoformat(),
                            },
                        )
                        await session.commit()
                        return result

                combined = await asyncio.gather(
                    *(submit("same-finish", payload) for _ in range(12)), mirror()
                )
                results = combined[:-1]
                assert all(result == results[0] for result in results)
                assert isinstance(results[0], dict)
                assert (
                    await submit(
                        "same-finish",
                        payload.model_copy(update={"time": Decimal("30.000")}),
                    )
                    == 409
                )
                assert await submit("different-key", payload) == 409
                async with AsyncSession(engine) as session:
                    assert len((await session.exec(select(Record))).all()) == 1
                    record = (await session.exec(select(Record))).one()
                    assert record.id == 998877 and record.uuid == payload.record_uuid
                    assert record.time == Decimal("35.288")
                    assert (
                        len((await session.exec(select(RecordUploadReceipt))).all())
                        == 1
                    )
                # API-key auditing must not serialize all instances behind a
                # long upload/scoring transaction from another instance.
                from app.api.v1.player_sessions import _get_server_group_from_api_key

                async with AsyncSession(engine, expire_on_commit=False) as first:
                    await _get_server_group_from_api_key(
                        session=first, x_server_group_key=api_key
                    )
                    await first.execute(
                        update(Player)
                        .where(Player.steamid64 == payload.steamid64)
                        .values(name="Long-running upload")
                    )
                    async with AsyncSession(engine, expire_on_commit=False) as second:

                        async def authenticate():
                            other = await _get_server_group_from_api_key(
                                session=second, x_server_group_key=api_key
                            )
                            await second.exec(
                                select(ServerGroup).where(ServerGroup.id == other.id)
                            )
                            await second.commit()
                            return other

                        authenticated = await asyncio.wait_for(
                            authenticate(), timeout=2
                        )
                        assert authenticated.last_api_key_used_at is not None
                    await first.rollback()
                # Even an administrative group-row lock must not block auth.
                async with AsyncSession(engine, expire_on_commit=False) as first:
                    await first.exec(
                        select(ServerGroup)
                        .where(ServerGroup.id == group_id)
                        .with_for_update()
                    )
                    async with AsyncSession(engine, expire_on_commit=False) as second:
                        authenticated = await asyncio.wait_for(
                            _get_server_group_from_api_key(
                                session=second, x_server_group_key=api_key
                            ),
                            timeout=2,
                        )
                        assert authenticated.id == group_id
                    await first.rollback()
            finally:
                await engine.dispose()

        asyncio.run(asyncio.wait_for(exercise(), timeout=60))
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()
