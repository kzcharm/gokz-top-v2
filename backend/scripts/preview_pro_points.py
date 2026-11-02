"""Export a read-only OVR PRO rarity preview for selected validated main maps."""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings  # noqa: E402
from app.core.db import async_engine, async_session_maker  # noqa: E402
from app.crud.record_filter import load_scoped_course_tiers  # noqa: E402
from app.models import ModeScope  # noqa: E402
from app.services.pro_points_candidate import (  # noqa: E402
    PRO_RARITY_STRENGTH,
    PRO_SMOOTHING_FINISHERS,
    pro_rank_points_candidate,
)
from app.services.rank_points_candidate import rank_points_candidate  # noqa: E402

DEFAULT_MAPS = [
    "kz_mz",
    "kz_man_everest_go_fix",
    "kz_ominous2",
    "kzpro_justrun_sp",
    "kz_suomi",
    "kz_imaginary_final",
    "kz_kiwitech",
    "kz_lionheart",
    "kz_unmake",
    "kz_kiwiterror",
]


async def preview(
    names: list[str], strength: float, smoothing: float
) -> dict[str, Any]:
    if settings.ENVIRONMENT != "local" or settings.POSTGRES_SERVER not in {
        "localhost",
        "127.0.0.1",
    }:
        raise ValueError("PRO point previews require the local database")
    names = list(dict.fromkeys(names))
    async with async_session_maker() as session:
        await session.execute(
            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        )
        maps = (
            await session.execute(
                text("""SELECT m.name,m.id,c.id
            FROM map m JOIN map_course c ON c.map_id=m.id AND c.stage=0
            WHERE m.name=ANY(CAST(:names AS text[])) AND m.validated=true"""),
                {"names": names},
            )
        ).all()
        if {row[0] for row in maps} != set(names):
            raise ValueError("All requested maps must have a validated main course")
        tiers = await load_scoped_course_tiers(
            session=session,
            scope=ModeScope.OVR,
            course_keys=[(m, 0) for _, m, _ in maps],
        )
        rows = (
            await session.execute(
                text("""SELECT p.course_id,p.type::text,p.steamid64
            FROM record_pb p WHERE p.scope='OVR'
              AND p.course_id=ANY(CAST(:courses AS integer[]))
              AND NOT EXISTS(SELECT 1 FROM ban b WHERE b.steamid64=p.steamid64
                AND (b.expires_at IS NULL OR b.expires_at>=CURRENT_TIMESTAMP))
            ORDER BY p.course_id,p.type,p.time,p.record_uuid"""),
                {"courses": [c for _, _, c in maps]},
            )
        ).all()
    buckets: dict[tuple[int, str], list[int]] = {}
    for course, kind, player in rows:
        buckets.setdefault((course, kind), []).append(player)
    output = []
    for name in names:
        _, map_id, course = next(row for row in maps if row[0] == name)
        tier = tiers[map_id, 0]
        if tier not in range(1, 9):
            raise ValueError(f"{name} has no eligible OVR tier")
        nub = buckets.get((course, "NUB"), [])
        pro = buckets.get((course, "PRO"), [])
        if not pro or not set(pro).issubset(nub):
            raise ValueError(
                f"{name} needs PRO records wholly contained in its NUB finisher population"
            )
        if len(nub) != len(set(nub)) or len(pro) != len(set(pro)):
            raise ValueError(f"Duplicate finishers in {name}")
        nub_scores = {
            player: rank_points_candidate(rank=r, total=len(nub), tier=tier)
            for r, player in enumerate(nub, 1)
        }
        baseline = [
            rank_points_candidate(rank=r, total=len(pro), tier=tier)
            for r in range(1, len(pro) + 1)
        ]
        proposed = [
            pro_rank_points_candidate(
                rank=r,
                pro_finishers=len(pro),
                nub_finishers=len(nub),
                tier=tier,
                rarity_strength=strength,
                smoothing_finishers=smoothing,
            )
            for r in range(1, len(pro) + 1)
        ]
        sampled = sorted(
            {
                1,
                len(pro),
                *range(2, min(11, len(pro) + 1)),
                *(max(1, round(i * len(pro) / 100)) for i in range(1, 101)),
            }
        )
        gains = [
            max(0, score - nub_scores[player])
            for player, score in zip(pro, proposed, strict=True)
        ]
        output.append(
            {
                "name": name,
                "tier": tier,
                "nub": len(nub),
                "pro": len(pro),
                "pro_share": len(pro) / len(nub),
                "effective_share": (len(pro) + smoothing) / (len(nub) + smoothing),
                "retained_tail": ((len(pro) + smoothing) / (len(nub) + smoothing))
                ** strength,
                "baseline_min": min(baseline),
                "proposed_min": min(proposed),
                "baseline_median": median(baseline),
                "proposed_median": median(proposed),
                "median_rarity_bonus": median(
                    [b - a for a, b in zip(baseline, proposed, strict=True)]
                ),
                "above900": sum(v >= 900 for v in proposed),
                "improves_nub_pb": sum(g > 0 for g in gains),
                "median_best_map_gain": median(gains),
                "curve": [
                    {
                        "rank": r,
                        "x": 100 * (r - 0.5) / len(pro),
                        "baseline": baseline[r - 1],
                        "proposed": proposed[r - 1],
                    }
                    for r in sampled
                ],
            }
        )
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "scope": "OVR",
        "source": "Read-only PB snapshot; validated main courses; active bans excluded; one PB per player per bucket",
        "rarity_strength": strength,
        "smoothing_finishers": smoothing,
        "stored_points_changed": False,
        "maps": output,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maps", nargs="+", default=DEFAULT_MAPS)
    parser.add_argument("--strength", type=float, default=PRO_RARITY_STRENGTH)
    parser.add_argument("--smoothing", type=float, default=PRO_SMOOTHING_FINISHERS)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = await preview(args.maps, args.strength, args.smoothing)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
        print(  # noqa: T201
            json.dumps(
                [{k: v for k, v in m.items() if k != "curve"} for m in result["maps"]],
                indent=2,
            )
        )
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
