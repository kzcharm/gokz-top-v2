import logging
import platform
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app import crud
from app.core.db import async_session_maker
from app.models import RecordScope, RecordScopeId
from app.tasks.build.points import rebuild_record_pb_points

logger = logging.getLogger(__name__)

_MACOS_FINISHED_SOUND = "/System/Library/Sounds/Glass.aiff"


@dataclass(frozen=True, slots=True)
class LeaderboardRebuildResult:
    selected: int
    created: int
    updated: int


@dataclass(frozen=True, slots=True)
class RatingBuildResult:
    full: bool
    pb_points_updated: int
    leaderboard: LeaderboardRebuildResult


def _get_tqdm() -> Any:
    try:
        from tqdm import tqdm  # type: ignore[import-untyped]
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing dependency 'tqdm'. Run `cd backend && uv sync` first."
        ) from exc
    return tqdm


def resolve_scope_ids(scope_names: Sequence[str] | None) -> list[int] | None:
    if not scope_names:
        return None
    return [int(RecordScopeId[name]) for name in scope_names]


def _play_completion_sound() -> None:
    if platform.system() != "Darwin":
        return

    try:
        completed = subprocess.run(
            ["afplay", _MACOS_FINISHED_SOUND],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        logger.warning("Skipping completion sound because `afplay` is unavailable.")
        return

    if completed.returncode != 0:
        logger.warning(
            "Completion sound failed with code=%s stderr=%s",
            completed.returncode,
            completed.stderr.strip(),
        )


async def rebuild_leaderboard_rows(
    *,
    scope_ids: Sequence[int] | None,
    steamid64s: Sequence[int] | None,
    limit: int | None,
    prioritize_existing_rating: bool = False,
) -> LeaderboardRebuildResult:
    steamid64_list = list(steamid64s) if steamid64s is not None else None

    async with async_session_maker() as session:
        keys = await crud.load_leaderboard_player_keys(
            session=session,
            scope_ids=scope_ids,
            steamid64s=steamid64_list,
            prioritize_existing_rating=prioritize_existing_rating,
        )

    if limit is not None:
        keys = keys[:limit]

    if not keys:
        logger.warning("No leaderboard_player rows matched the selected filters.")
        return LeaderboardRebuildResult(selected=0, created=0, updated=0)

    logger.info("Rebuilding %s leaderboard_player row(s)", len(keys))
    tqdm = _get_tqdm()
    total_created = 0
    total_updated = 0
    progress = tqdm(keys, total=len(keys), desc="leaderboard rows", unit="row")
    for scope_id, steamid64 in progress:
        async with async_session_maker() as session:
            created, updated = await crud.rebuild_leaderboard_players_for_keys(
                session=session,
                keys=[(scope_id, steamid64)],
            )
            await session.commit()
        total_created += created
        total_updated += updated
        progress.set_postfix_str(
            f"scope={RecordScopeId(scope_id).name} steamid64={steamid64}"
        )

    logger.info(
        "Finished rebuilding leaderboard_player rows=%s created=%s updated=%s",
        len(keys),
        total_created,
        total_updated,
    )
    return LeaderboardRebuildResult(
        selected=len(keys),
        created=total_created,
        updated=total_updated,
    )


async def rebuild_ratings(
    *,
    scope_ids: Sequence[int] | None,
    scopes: Sequence[RecordScope] | None,
    steamid64s: Sequence[int] | None,
    limit: int | None,
    full: bool,
) -> RatingBuildResult:
    pb_points_updated = 0
    if full:
        if not scopes:
            raise ValueError("Full rating rebuild requires at least one scope.")
        pb_points_updated = await rebuild_record_pb_points(
            scopes=scopes,
            map_names=None,
            stage=0,
            limit=None,
        )

    leaderboard = await rebuild_leaderboard_rows(
        scope_ids=scope_ids,
        steamid64s=steamid64s,
        limit=limit,
        prioritize_existing_rating=full,
    )
    if full:
        _play_completion_sound()
    return RatingBuildResult(
        full=full,
        pb_points_updated=pb_points_updated,
        leaderboard=leaderboard,
    )
