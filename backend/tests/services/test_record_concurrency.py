"""Exercise real commit boundaries with independent PostgreSQL connections."""

import asyncio
import os
import subprocess
import sys
import uuid
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import Session, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import init_db
from app.models import Record, RecordUploadReceipt, ServerGroup
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
                    group, _, payload = await setup_finish(session)
                    group_id = group.id
                    await session.commit()

                async def submit(key, finish):
                    async with AsyncSession(engine, expire_on_commit=False) as session:
                        group = await session.get(ServerGroup, group_id)
                        try:
                            return await accept_record(session, group, finish, key)
                        except HTTPException as exc:
                            await session.rollback()
                            return exc.status_code

                results = await asyncio.gather(
                    *(submit("same-finish", payload) for _ in range(12))
                )
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
                    assert (
                        len((await session.exec(select(RecordUploadReceipt))).all())
                        == 1
                    )
            finally:
                await engine.dispose()

        asyncio.run(asyncio.wait_for(exercise(), timeout=60))
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()
