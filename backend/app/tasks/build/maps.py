from collections.abc import Sequence
from dataclasses import dataclass

from app import crud
from app.core.db import async_session_maker
from app.models import ModeScope

__all__ = ["MapLeaderboardRebuildResult", "rebuild_map_leaderboards"]


@dataclass(frozen=True, slots=True)
class MapLeaderboardRebuildResult:
    scopes: tuple[ModeScope, ...]
    map_ids: tuple[int, ...]
    rows_rebuilt: int


async def rebuild_map_leaderboards(
    *,
    scopes: Sequence[ModeScope] | None,
    map_ids: Sequence[int] | None,
) -> MapLeaderboardRebuildResult:
    normalized_scopes = tuple(scopes or tuple(ModeScope))
    normalized_map_ids = tuple(dict.fromkeys(map_ids or ()))

    async with async_session_maker() as session:
        rows_rebuilt = await crud.rebuild_map_leaderboards(
            session=session,
            scopes=normalized_scopes,
            map_ids=normalized_map_ids or None,
        )
        await session.commit()

    return MapLeaderboardRebuildResult(
        scopes=normalized_scopes,
        map_ids=normalized_map_ids,
        rows_rebuilt=rows_rebuilt,
    )
