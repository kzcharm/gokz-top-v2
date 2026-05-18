from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Map, Record
from app.services.run_replay_parser import ParsedRunReplay

REPLAY_MATCH_WINDOW = timedelta(hours=24)


@dataclass(frozen=True)
class RunReplayCandidateMatch:
    record: Record
    created_at_delta: timedelta


@dataclass(frozen=True)
class RunReplayMatchResult:
    replay: ParsedRunReplay
    match: RunReplayCandidateMatch | None
    is_ambiguous: bool
    candidates: tuple[RunReplayCandidateMatch, ...]


async def find_run_replay_record_candidates(
    *,
    session: AsyncSession,
    replay: ParsedRunReplay,
) -> list[RunReplayCandidateMatch]:
    lower_bound = replay.recorded_at - REPLAY_MATCH_WINDOW
    upper_bound = replay.recorded_at + REPLAY_MATCH_WINDOW

    statement = (
        select(Record)
        .join(Map, col(Record.map_id) == col(Map.id))
        .where(
            col(Record.steamid64) == replay.steamid64,
            col(Record.mode) == replay.mode,
            col(Map.name) == replay.map_name,
            col(Record.stage) == replay.course,
            col(Record.time) == replay.time,
            col(Record.created_at) >= lower_bound,
            col(Record.created_at) <= upper_bound,
        )
        .order_by(col(Record.created_at).asc(), col(Record.uuid).asc())
    )
    records = list((await session.exec(statement)).all())
    return [
        RunReplayCandidateMatch(
            record=record,
            created_at_delta=abs(record.created_at - replay.recorded_at),
        )
        for record in records
    ]


async def match_record_for_run_replay(
    *,
    session: AsyncSession,
    replay: ParsedRunReplay,
) -> RunReplayMatchResult:
    candidates = await find_run_replay_record_candidates(
        session=session,
        replay=replay,
    )
    if not candidates:
        return RunReplayMatchResult(
            replay=replay,
            match=None,
            is_ambiguous=False,
            candidates=(),
        )

    ordered = tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                candidate.created_at_delta,
                candidate.record.created_at,
                candidate.record.uuid,
            ),
        )
    )
    best = ordered[0]
    is_ambiguous = (
        len(ordered) > 1 and ordered[1].created_at_delta == best.created_at_delta
    )
    return RunReplayMatchResult(
        replay=replay,
        match=None if is_ambiguous else best,
        is_ambiguous=is_ambiguous,
        candidates=ordered,
    )
