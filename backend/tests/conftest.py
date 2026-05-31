import asyncio
import os
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlmodel import Session, delete
from sqlmodel.ext.asyncio.session import AsyncSession

os.environ["ENABLE_TEST_AUTH_HELPERS"] = "true"

from app.api.deps import get_db
from app.core.config import settings
from app.core.db import (
    LOCAL_DEV_SUPERUSER_TEST_WEBHOOK_URL,
    async_engine,
    engine,
    init_db,
)
from app.main import app
from app.models import PlayerProfileView, PlayerWebhook, User
from app.services.server_status import maintain_server_heartbeat_partitions
from tests.utils.user import authentication_token_from_steamid
from tests.utils.utils import get_superuser_token_headers, random_steamid64


def _is_safe_test_database_name(name: str) -> bool:
    normalized = name.strip().lower()
    return normalized.startswith("test_") or normalized.endswith("_test")


def _upgrade_test_database() -> None:
    alembic_config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(alembic_config, "head")


async def _maintain_test_server_heartbeat_partitions() -> None:
    async with AsyncSession(async_engine) as session:
        await maintain_server_heartbeat_partitions(session=session)


@pytest.fixture(scope="session", autouse=True)
def ensure_safe_test_database() -> None:
    """
    Block test runs against non-local environments/databases.
    This prevents accidental writes to staging/production databases.
    """
    if settings.ENVIRONMENT != "local" or settings.POSTGRES_SERVER not in {
        "localhost",
        "127.0.0.1",
    }:
        raise RuntimeError(
            "Refusing to run tests outside local DB environment. "
            f"ENVIRONMENT={settings.ENVIRONMENT!r}, POSTGRES_SERVER={settings.POSTGRES_SERVER!r}"
        )
    if not _is_safe_test_database_name(settings.POSTGRES_DB):
        raise RuntimeError(
            "Refusing to run tests against a non-test local database. "
            f"POSTGRES_DB={settings.POSTGRES_DB!r}. "
            "Use a dedicated database named like 'app_test' or 'test_app'."
        )


@pytest.fixture(scope="session", autouse=True)
def setup_db() -> Generator[None]:
    _upgrade_test_database()
    asyncio.run(_maintain_test_server_heartbeat_partitions())
    with Session(engine) as session:
        init_db(session)

    yield

    with Session(engine) as session:
        session.execute(delete(PlayerProfileView))
        session.execute(delete(User))
        session.commit()


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession]:
    async with async_engine.connect() as connection:
        transaction = await connection.begin()
        async with AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        ) as session:
            try:
                await session.exec(
                    delete(PlayerWebhook).where(
                        PlayerWebhook.url == LOCAL_DEV_SUPERUSER_TEST_WEBHOOK_URL
                    )
                )
                yield session
            finally:
                await session.close()
                await transaction.rollback()


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient]:
    async def _get_test_db() -> AsyncGenerator[AsyncSession]:
        yield db

    app.dependency_overrides[get_db] = _get_test_db
    previous_collector_setting = settings.RUN_SERVER_STATUS_COLLECTOR_IN_APP
    previous_globalapi_sync_setting = settings.RUN_GLOBALAPI_SYNC_RUNNER_IN_APP
    previous_daily_rank_pipeline_setting = (
        settings.RUN_DAILY_RANK_PIPELINE_TASK_RUNNER_IN_APP
    )
    previous_player_session_timeout_setting = (
        settings.RUN_PLAYER_SESSION_TIMEOUT_RUNNER_IN_APP
    )
    previous_live_stream_runner_setting = settings.RUN_LIVE_STREAM_RUNNER_IN_APP
    previous_jump_replay_cleanup_runner_setting = (
        settings.RUN_JUMP_REPLAY_CLEANUP_RUNNER_IN_APP
    )
    settings.RUN_SERVER_STATUS_COLLECTOR_IN_APP = False
    settings.RUN_GLOBALAPI_SYNC_RUNNER_IN_APP = False
    settings.RUN_DAILY_RANK_PIPELINE_TASK_RUNNER_IN_APP = False
    settings.RUN_PLAYER_SESSION_TIMEOUT_RUNNER_IN_APP = False
    settings.RUN_LIVE_STREAM_RUNNER_IN_APP = False
    settings.RUN_JUMP_REPLAY_CLEANUP_RUNNER_IN_APP = False
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c
    finally:
        settings.RUN_SERVER_STATUS_COLLECTOR_IN_APP = previous_collector_setting
        settings.RUN_GLOBALAPI_SYNC_RUNNER_IN_APP = previous_globalapi_sync_setting
        settings.RUN_DAILY_RANK_PIPELINE_TASK_RUNNER_IN_APP = (
            previous_daily_rank_pipeline_setting
        )
        settings.RUN_PLAYER_SESSION_TIMEOUT_RUNNER_IN_APP = (
            previous_player_session_timeout_setting
        )
        settings.RUN_LIVE_STREAM_RUNNER_IN_APP = previous_live_stream_runner_setting
        settings.RUN_JUMP_REPLAY_CLEANUP_RUNNER_IN_APP = (
            previous_jump_replay_cleanup_runner_setting
        )
        app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def superuser_token_headers(client: AsyncClient) -> dict[str, str]:
    return await get_superuser_token_headers(client)


@pytest_asyncio.fixture
async def normal_user_token_headers(
    client: AsyncClient, db: AsyncSession
) -> dict[str, str]:
    return await authentication_token_from_steamid(
        client=client,
        steamid64=random_steamid64(),
        db=db,
    )
