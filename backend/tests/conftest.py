from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel import Session, delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import async_session_maker, engine, init_db
from app.main import app
from app.models import Item, User
from tests.utils.user import authentication_token_from_steamid
from tests.utils.utils import get_superuser_token_headers, random_steamid64


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
    async with async_session_maker() as session:
        yield session


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


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
