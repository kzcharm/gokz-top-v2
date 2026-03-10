from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel import Session, delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import get_db
from app.core.config import settings
from app.core.db import async_engine, engine, init_db
from app.main import app
from app.models import Item, User
from tests.utils.user import authentication_token_from_steamid
from tests.utils.utils import get_superuser_token_headers, random_steamid64


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


@pytest.fixture(scope="session", autouse=True)
def setup_db() -> Generator[None]:
    with Session(engine) as session:
        init_db(session)

    yield

    with Session(engine) as session:
        session.execute(delete(Item))
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
                yield session
            finally:
                await session.close()
                await transaction.rollback()


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient]:
    async def _get_test_db() -> AsyncGenerator[AsyncSession]:
        yield db

    app.dependency_overrides[get_db] = _get_test_db
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c
    finally:
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
