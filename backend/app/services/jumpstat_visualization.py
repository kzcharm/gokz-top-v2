from __future__ import annotations

import uuid

from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Jumpstat, JumpstatVisualizationPublic
from app.services.jump_replay_parser import (
    JUMPSTAT_VISUALIZATION_VERSION,
    JumpReplayParseError,
    parse_jump_replay_visualization,
)
from app.services.jump_replay_storage import load_jump_replay


class JumpstatVisualizationUnavailableError(RuntimeError):
    pass


def _validate_cached_visualization(
    visualization_data: dict[str, object] | None,
) -> JumpstatVisualizationPublic | None:
    if visualization_data is None:
        return None

    if visualization_data.get("version") != JUMPSTAT_VISUALIZATION_VERSION:
        return None
    try:
        return JumpstatVisualizationPublic.model_validate(visualization_data)
    except ValidationError:
        return None


async def get_or_build_jumpstat_visualization(
    *,
    session: AsyncSession,
    jumpstat: Jumpstat,
) -> JumpstatVisualizationPublic:
    cached = _validate_cached_visualization(jumpstat.visualization_data)
    if cached is not None:
        return cached

    try:
        replay_bytes = load_jump_replay(jumpstat_id=jumpstat.id)
        visualization = parse_jump_replay_visualization(
            data=replay_bytes,
            source_name=f"{jumpstat.id}.replay",
        )
    except (FileNotFoundError, JumpReplayParseError) as exc:
        raise JumpstatVisualizationUnavailableError(str(exc)) from exc

    jumpstat.visualization_data = visualization.model_dump(mode="json")
    session.add(jumpstat)
    await session.commit()
    await session.refresh(jumpstat)
    return visualization


async def read_jumpstat_visualization(
    *,
    session: AsyncSession,
    jumpstat_id: uuid.UUID,
) -> JumpstatVisualizationPublic | None:
    jumpstat = await session.get(Jumpstat, jumpstat_id)
    if jumpstat is None:
        return None
    return await get_or_build_jumpstat_visualization(session=session, jumpstat=jumpstat)
