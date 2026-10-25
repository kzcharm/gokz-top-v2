"""Shared native-record availability and minimum mode-version checks."""

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import KZMode, RecordFilter


async def available_record_filter_modes(
    session: AsyncSession,
    *,
    map_id: int,
    stage: int,
    tickrate: int = 128,
    teleports: int | None = None,
) -> set[KZMode]:
    """Only exact filters grant availability; zero-TP runs fit either category.

    Preflight and heartbeat payloads have no teleport count and report whether
    either category is available. Final acceptance checks the actual finish.
    """
    statement = select(RecordFilter.mode).where(
        RecordFilter.map_id == map_id,
        RecordFilter.stage == stage,
        RecordFilter.tickrate == tickrate,
    )
    if teleports is not None and teleports > 0:
        statement = statement.where(col(RecordFilter.has_teleports).is_(True))
    return {KZMode(mode) for mode in (await session.exec(statement)).all()}


def mode_version_supported(*, submitted: int, minimum: int | None) -> bool:
    return minimum is not None and submitted > 0 and submitted >= minimum
