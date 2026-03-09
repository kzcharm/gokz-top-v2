from datetime import UTC, datetime

from sqlmodel import Session, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import CANONICAL_MODE_SEEDS, Mode, ModeAdminUpdate, ModePublic


def _get_datetime_utc() -> datetime:
    return datetime.now(UTC)


def _sync_canonical_modes_with_session(session: Session) -> None:
    now = _get_datetime_utc()
    has_changes = False
    for seed in CANONICAL_MODE_SEEDS:
        statement = select(Mode).where(Mode.id == seed.id)
        db_mode = session.exec(statement).first()

        if not db_mode:
            session.add(
                Mode(
                    id=seed.id,
                    name=seed.name,
                    name_short=seed.name_short,
                    id_plugin=seed.id_plugin,
                    description=seed.description,
                    latest_version=seed.latest_version,
                    latest_version_description=seed.latest_version_description,
                    website=seed.website,
                    repo=seed.repo,
                    contact_steamid64=seed.contact_steamid64,
                    created_on=now,
                    updated_on=now,
                    updated_by_id=seed.updated_by_id,
                )
            )
            has_changes = True
            continue

        if (
            db_mode.name != seed.name
            or db_mode.name_short != seed.name_short
            or db_mode.id_plugin != seed.id_plugin
        ):
            db_mode.name = seed.name
            db_mode.name_short = seed.name_short
            db_mode.id_plugin = seed.id_plugin
            db_mode.updated_on = now
            session.add(db_mode)
            has_changes = True

    if has_changes:
        session.commit()


def sync_canonical_modes_sync(*, session: Session) -> None:
    _sync_canonical_modes_with_session(session)


async def sync_canonical_modes(*, session: AsyncSession) -> None:
    now = _get_datetime_utc()
    has_changes = False
    for seed in CANONICAL_MODE_SEEDS:
        statement = select(Mode).where(Mode.id == seed.id)
        db_mode = (await session.exec(statement)).first()

        if not db_mode:
            session.add(
                Mode(
                    id=seed.id,
                    name=seed.name,
                    name_short=seed.name_short,
                    id_plugin=seed.id_plugin,
                    description=seed.description,
                    latest_version=seed.latest_version,
                    latest_version_description=seed.latest_version_description,
                    website=seed.website,
                    repo=seed.repo,
                    contact_steamid64=seed.contact_steamid64,
                    created_on=now,
                    updated_on=now,
                    updated_by_id=seed.updated_by_id,
                )
            )
            has_changes = True
            continue

        if (
            db_mode.name != seed.name
            or db_mode.name_short != seed.name_short
            or db_mode.id_plugin != seed.id_plugin
        ):
            db_mode.name = seed.name
            db_mode.name_short = seed.name_short
            db_mode.id_plugin = seed.id_plugin
            db_mode.updated_on = now
            session.add(db_mode)
            has_changes = True

    if has_changes:
        await session.commit()


async def read_modes(*, session: AsyncSession) -> list[Mode]:
    statement = select(Mode).order_by(col(Mode.id).asc())
    return list((await session.exec(statement)).all())


async def get_mode_by_id(*, session: AsyncSession, id: int) -> Mode | None:
    return await session.get(Mode, id)


async def get_mode_by_name(*, session: AsyncSession, mode_name: str) -> Mode | None:
    statement = select(Mode).where(Mode.name == mode_name)
    return (await session.exec(statement)).first()


async def update_mode_metadata(
    *,
    session: AsyncSession,
    db_mode: Mode,
    mode_in: ModeAdminUpdate,
    updated_by_id: int,
) -> Mode:
    mode_data = mode_in.model_dump(exclude_unset=True)
    if mode_data.get("contact_steamid64") is not None:
        mode_data["contact_steamid64"] = int(mode_data["contact_steamid64"])

    db_mode.sqlmodel_update(mode_data)
    db_mode.updated_on = _get_datetime_utc()
    db_mode.updated_by_id = updated_by_id
    session.add(db_mode)
    await session.commit()
    await session.refresh(db_mode)
    return db_mode


def to_mode_public(*, mode: Mode) -> ModePublic:
    return ModePublic(
        id=mode.id,
        name=mode.name,
        name_short=mode.name_short,
        id_plugin=mode.id_plugin,
        description=mode.description,
        latest_version=mode.latest_version,
        latest_version_description=mode.latest_version_description,
        website=mode.website,
        repo=mode.repo,
        contact_steamid64=str(mode.contact_steamid64),
        supported_tickrates=None,
        created_on=mode.created_on,
        updated_on=mode.updated_on,
        updated_by_id=str(mode.updated_by_id),
    )
