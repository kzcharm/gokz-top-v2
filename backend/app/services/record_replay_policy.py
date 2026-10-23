"""Pure replay admission rules; callers persist decisions with accepted records."""

from dataclasses import dataclass
from decimal import Decimal

from app.models.mode_scope import ModeScope, mode_scope_modes
from app.models.record import KZMode, RecordType


def effective_record_filter_mode(mode: KZMode) -> KZMode:
    """NKZ shares KZT eligibility while retaining its own recorded mode."""
    return KZMode.KZT if mode is KZMode.NKZ else mode


@dataclass(frozen=True)
class ReplayBucketResult:
    scope: ModeScope
    type: RecordType
    previous_pb: Decimal | None
    previous_wr: Decimal | None
    rank: int


def qualifies_for_run_replay(
    *,
    mode: KZMode,
    stage: int,
    teleports: int,
    time: Decimal,
    buckets: list[ReplayBucketResult],
) -> bool:
    """Evaluate admission once, against pre-insert bests and post-insert ranks.

    A synchronized copy of the same run must be excluded from previous bests.
    Callers must exclude banned/invalid runs from both bests and ranks.
    """
    if stage < 0 or teleports < 0 or not time.is_finite() or time <= 0:
        return False
    for bucket in buckets:
        if mode not in mode_scope_modes(bucket.scope) or bucket.rank < 1:
            continue
        if bucket.type is RecordType.PRO and teleports != 0:
            continue
        if bucket.previous_pb is not None and time >= bucket.previous_pb:
            continue
        if stage > 0:
            if bucket.rank == 1 and (
                bucket.previous_wr is None or time < bucket.previous_wr
            ):
                return True
        elif bucket.rank <= (50 if bucket.scope is ModeScope.OVR else 10):
            return True
    return False
