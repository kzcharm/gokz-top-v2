"""Explicit, per-scope population calibration of skill display ratings."""

from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import func
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import col, select

from app.core.db import async_session_maker
from app.core.rank_system import get_rank_system_settings
from app.crud.ban import not_active_ban_exists_split_clause
from app.models import LeaderboardPlayer, ModeScope, SkillRatingConverter
from app.models.utils import get_datetime_utc
from app.services.skill_rating import SKILLS
from app.services.skill_rating_converter import Calibration, calibrate


@dataclass(frozen=True)
class CalibrationResult:
    scope: ModeScope
    skill: str
    population: int
    positive: int
    ties: int
    calibration: Calibration | None


async def calibrate_skill_converters(
    *, scopes: tuple[ModeScope, ...], save: bool = False
) -> list[CalibrationResult]:
    results: list[CalibrationResult] = []
    max_raw_rating = get_rank_system_settings().rating.target_max_raw_rating
    async with async_session_maker() as session:
        for scope in scopes:
            for skill in SKILLS:
                column = getattr(LeaderboardPlayer, f"rating_{skill}")
                histogram = (
                    await session.exec(
                        select(column, func.count())
                        .where(
                            col(LeaderboardPlayer.scope) == scope,
                            not_active_ban_exists_split_clause(
                                steamid64_column=cast(
                                    ColumnElement[Any], col(LeaderboardPlayer.steamid64)
                                )
                            ),
                        )
                        .group_by(column)
                        .order_by(column)
                    )
                ).all()
                counts = [(int(raw), int(count)) for raw, count in histogram]
                population = sum(count for _raw, count in counts)
                positive = sum(count for raw, count in counts if raw > 0)
                ties = sum(max(count - 1, 0) for _raw, count in counts)
                try:
                    calibration = calibrate(
                        counts,
                        max_raw_rating=max_raw_rating,
                    )
                except ValueError:
                    calibration = None
                results.append(
                    CalibrationResult(
                        scope=scope,
                        skill=skill,
                        population=population,
                        positive=positive,
                        ties=ties,
                        calibration=calibration,
                    )
                )
                if not save or calibration is None:
                    continue
                row = await session.get(SkillRatingConverter, (scope, skill))
                if row is None:
                    row = SkillRatingConverter(
                        scope=scope,
                        skill=skill,
                        anchors=calibration.anchors,
                        sample_size=calibration.population,
                    )
                else:
                    row.anchors = calibration.anchors
                    row.sample_size = calibration.population
                    row.updated_at = get_datetime_utc()
                session.add(row)
        if save:
            await session.commit()
    return results
