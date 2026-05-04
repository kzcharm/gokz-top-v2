from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import Session, create_engine, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import crud
from app.core.config import settings
from app.models import Player, User, UserRole

database_uri = str(settings.SQLALCHEMY_DATABASE_URI)

engine = create_engine(database_uri)
async_engine = create_async_engine(database_uri)
async_session_maker = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# make sure all SQLModel models are imported (app.models) before initializing DB
# otherwise, SQLModel might fail to initialize relationships properly
# for more details: https://github.com/fastapi/full-stack-fastapi-template/issues/28


def init_db(session: Session) -> None:
    # Tables should be created with Alembic migrations
    # But if you don't want to use migrations, create
    # the tables un-commenting the next lines
    # from sqlmodel import SQLModel

    # This works because the models are already imported and registered from app.models
    # SQLModel.metadata.create_all(engine)

    crud.sync_canonical_modes_sync(session=session)

    player_statement = select(Player).where(Player.steamid64 == settings.SUPER_USER_STEAMID64)
    if not session.exec(player_statement).first():
        session.add(
            Player(
                steamid64=settings.SUPER_USER_STEAMID64,
                name=str(settings.SUPER_USER_STEAMID64),
            )
        )
        session.commit()

    statement = select(User).where(User.steamid64 == settings.SUPER_USER_STEAMID64)
    if session.exec(statement).first():
        return

    session.add(
        User(
            steamid64=settings.SUPER_USER_STEAMID64,
            is_active=True,
            roles=[UserRole.SUPERUSER],
        )
    )
    session.commit()


async def init_db_async(session: AsyncSession) -> None:
    await crud.sync_canonical_modes(session=session)
    await crud.get_or_create_user_from_steam(
        session=session,
        steamid64=settings.SUPER_USER_STEAMID64,
    )
