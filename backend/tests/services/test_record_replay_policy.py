from decimal import Decimal

import pytest

from app.models.mode_scope import ModeScope
from app.models.record import KZMode, RecordType
from app.services.record_replay_policy import (
    ReplayBucketResult,
    effective_record_filter_mode,
    qualifies_for_run_replay,
)


@pytest.mark.parametrize("mode", list(KZMode))
def test_filter_mode(mode: KZMode) -> None:
    assert effective_record_filter_mode(mode) == (
        KZMode.KZT if mode is KZMode.NKZ else mode
    )


@pytest.mark.parametrize(
    "mode,scope,rank,stage,previous_pb,previous_wr,teleports,kind,expected",
    [
        (KZMode.KZT, ModeScope.OVR, 50, 0, "20", "5", 1, RecordType.NUB, True),
        (KZMode.KZT, ModeScope.OVR, 51, 0, "20", "5", 0, RecordType.PRO, False),
        (KZMode.NKZ, ModeScope.KZT, 10, 0, "20", "5", 0, RecordType.PRO, True),
        (KZMode.NKZ, ModeScope.KZT, 11, 0, "20", "5", 0, RecordType.PRO, False),
        (KZMode.NKZ, ModeScope.VNL, 1, 0, "20", "15", 0, RecordType.PRO, False),
        (KZMode.VNL, ModeScope.VNL, 1, 1, "20", "15", 0, RecordType.PRO, True),
        (KZMode.SKZ, ModeScope.SKZ, 2, 1, "20", "5", 0, RecordType.PRO, False),
        (KZMode.SKZ, ModeScope.OVR, 1, 1, "20", "10", 0, RecordType.PRO, False),
        (KZMode.KZT, ModeScope.KZT, 1, 0, "10", "10", 0, RecordType.PRO, False),
        (KZMode.NKZ, ModeScope.KZT, 1, 1, None, None, 0, RecordType.PRO, True),
        (KZMode.NKZ, ModeScope.KZT, 1, 1, None, None, 1, RecordType.PRO, False),
        (KZMode.NKZ, ModeScope.KZT, 1, 1, None, None, 1, RecordType.NUB, True),
    ],
)
def test_replay_admission(
    mode: KZMode,
    scope: ModeScope,
    rank: int,
    stage: int,
    previous_pb: str | None,
    previous_wr: str | None,
    teleports: int,
    kind: RecordType,
    expected: bool,
) -> None:
    bucket = ReplayBucketResult(
        scope=scope,
        type=kind,
        rank=rank,
        previous_pb=Decimal(previous_pb) if previous_pb else None,
        previous_wr=Decimal(previous_wr) if previous_wr else None,
    )
    assert (
        qualifies_for_run_replay(
            mode=mode,
            stage=stage,
            teleports=teleports,
            time=Decimal("10"),
            buckets=[bucket],
        )
        is expected
    )
