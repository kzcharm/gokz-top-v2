"""Repair/backfill for the six leaderboard skill ratings."""

from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import func, text
from sqlmodel import col, select

from app.core.db import async_session_maker
from app.models import (
    LeaderboardPlayer,
    Map,
    MapCourse,
    MapSkill,
    ModeScope,
    RecordPb,
)
from app.services.skill_rating import SKILLS, calculate_skill_rating

BATCH_SIZE = 500


async def rebuild_all_skill_ratings(
    *, scopes: Sequence[ModeScope] | None = None, limit: int | None = None
) -> dict[ModeScope, int]:
    return await _rebuild_skill_ratings(
        scopes=scopes or tuple(ModeScope),
        limit=limit,
    )


async def _rebuild_skill_ratings(
    *, scopes: Sequence[ModeScope], limit: int | None
) -> dict[ModeScope, int]:
    updated: dict[ModeScope, int] = {}
    for scope in scopes:
        async with async_session_maker() as session:
            players = list(
                await session.exec(
                    select(LeaderboardPlayer)
                    .where(col(LeaderboardPlayer.scope) == scope)
                    .order_by(
                        col(LeaderboardPlayer.rating).desc(),
                        col(LeaderboardPlayer.steamid64),
                    )
                    .limit(limit)
                )
            )
            skill_rows = (await session.exec(select(MapSkill))).all()
            skills_by_map_id = {row.map_id: row for row in skill_rows}
            changed = 0
            for start in range(0, len(players), BATCH_SIZE):
                batch = players[start : start + BATCH_SIZE]
                steamid64s = [player.steamid64 for player in batch]
                await session.execute(text("SET LOCAL enable_seqscan = off"))
                pb_rows = (
                    await session.exec(
                        select(
                            col(RecordPb.steamid64),
                            col(MapCourse.map_id),
                            func.max(col(RecordPb.points)),
                        )
                        .join(
                            MapCourse,
                            col(RecordPb.course_id) == col(MapCourse.id),
                        )
                        .join(Map, col(MapCourse.map_id) == col(Map.id))
                        .where(
                            col(RecordPb.scope) == scope,
                            col(RecordPb.steamid64).in_(steamid64s),
                            col(MapCourse.stage) == 0,
                            col(Map.validated).is_(True),
                        )
                        .group_by(
                            col(RecordPb.steamid64),
                            col(MapCourse.map_id),
                        )
                    )
                ).all()
                ratings_input_by_player: dict[
                    int, dict[str, list[tuple[int, Decimal, int]]]
                ] = {
                    player.steamid64: {skill: [] for skill in SKILLS}
                    for player in batch
                }
                for steamid64, map_id, points in pb_rows:
                    analysis = skills_by_map_id.get(map_id)
                    if analysis is None:
                        continue
                    for skill in SKILLS:
                        ratings_input_by_player[steamid64][skill].append(
                            (int(points), getattr(analysis, skill), int(map_id))
                        )
                for player in batch:
                    values = {
                        skill: calculate_skill_rating(
                            ratings_input_by_player[player.steamid64][skill]
                        )
                        for skill in SKILLS
                    }
                    if any(
                        getattr(player, f"rating_{skill}") != values[skill]
                        for skill in SKILLS
                    ):
                        for skill in SKILLS:
                            setattr(player, f"rating_{skill}", values[skill])
                        session.add(player)
                        changed += 1
                await session.commit()
            updated[scope] = changed
    return updated
