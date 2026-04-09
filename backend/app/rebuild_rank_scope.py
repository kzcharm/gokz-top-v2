import argparse
import asyncio
import logging
import platform
import subprocess
from dataclasses import dataclass

from app.models import RecordScope, RecordScopeId
from app.rebuild_leaderboard_player import (
    LeaderboardRebuildResult,
    rebuild_leaderboard_rows,
)
from app.rebuild_record_pb_points import rebuild_record_pb_points

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_MACOS_FINISHED_SOUND = "/System/Library/Sounds/Glass.aiff"


@dataclass(frozen=True, slots=True)
class RankScopeRebuildResult:
    pb_points_updated: int
    leaderboard: LeaderboardRebuildResult


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rebuild rank-system PB points and leaderboard rows for selected scopes.",
    )
    parser.add_argument(
        "--scope",
        action="append",
        choices=[scope.name for scope in RecordScope],
        dest="scopes",
        required=True,
        help="Required scope filter. Repeat to rebuild multiple scopes.",
    )
    return parser


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


async def rebuild_rank_scopes(*, scopes: list[RecordScope]) -> RankScopeRebuildResult:
    pb_points_updated = await rebuild_record_pb_points(
        scopes=scopes,
        map_names=None,
        stage=0,
        limit=None,
    )
    leaderboard = await rebuild_leaderboard_rows(
        scope_ids=[int(RecordScopeId[scope.name]) for scope in scopes],
        steamid64s=None,
        limit=None,
        prioritize_existing_rating=True,
    )
    _play_completion_sound()
    return RankScopeRebuildResult(
        pb_points_updated=pb_points_updated,
        leaderboard=leaderboard,
    )


async def _main_async(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    scopes = [RecordScope[name] for name in args.scopes]
    result = await rebuild_rank_scopes(scopes=scopes)
    logger.info(
        "Finished rank scope rebuild pb_points_updated=%s leaderboard_rows=%s created=%s updated=%s",
        result.pb_points_updated,
        result.leaderboard.selected,
        result.leaderboard.created,
        result.leaderboard.updated,
    )


def main(argv: list[str] | None = None) -> None:
    asyncio.run(_main_async(argv))


if __name__ == "__main__":
    main()
