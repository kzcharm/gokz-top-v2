from collections import defaultdict

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.crud.leaderboard_player import read_player_leaderboard_rank
from app.crud.record import get_pb_record_publics
from app.models import (
    Map,
    MapCourse,
    MapCourseTier,
    ModeScope,
    Player,
    PlayerCompareRunPublic,
    PlayerCompareTierPublic,
    PlayerComparisonPublic,
    RecordPublic,
    RecordType,
    mode_scope_modes,
)


async def _read_main_map_tiers(
    *, session: AsyncSession, scope: ModeScope
) -> dict[int, int]:
    rows = (
        await session.exec(
            select(MapCourse.map_id, MapCourseTier.tier)
            .join(Map, col(MapCourse.map_id) == col(Map.id))
            .join(
                MapCourseTier,
                col(MapCourseTier.course_id) == col(MapCourse.id),
            )
            .where(
                col(MapCourse.stage) == 0,
                col(Map.validated).is_(True),
                col(MapCourseTier.mode).in_(list(mode_scope_modes(scope))),
                col(MapCourseTier.tier) > 0,
            )
        )
    ).all()
    tiers: dict[int, int] = {}
    for map_id, tier in rows:
        tiers[int(map_id)] = min(tiers.get(int(map_id), int(tier)), int(tier))
    return tiers


def _build_run_rows(
    *,
    player1_records: list[RecordPublic],
    player2_records: list[RecordPublic],
) -> list[PlayerCompareRunPublic]:
    player1_by_map = {record.map_id: record for record in player1_records}
    player2_by_map = {record.map_id: record for record in player2_records}
    rows: list[PlayerCompareRunPublic] = []
    for map_id in player1_by_map.keys() | player2_by_map.keys():
        player1_record = player1_by_map.get(map_id)
        player2_record = player2_by_map.get(map_id)
        reference = player1_record or player2_record
        if reference is None:
            continue
        rows.append(
            PlayerCompareRunPublic(
                map_id=map_id,
                map_name=reference.map_name,
                map_tier=reference.map_tier,
                player1=player1_record,
                player2=player2_record,
                time_delta=(
                    player1_record.time - player2_record.time
                    if player1_record is not None and player2_record is not None
                    else None
                ),
                points_delta=(
                    player1_record.points - player2_record.points
                    if player1_record is not None and player2_record is not None
                    else None
                ),
            )
        )
    return rows


async def read_player_comparison(
    *,
    session: AsyncSession,
    player1: Player,
    player2: Player,
    scope: ModeScope,
) -> PlayerComparisonPublic:
    player1_rank = await read_player_leaderboard_rank(
        session=session, player=player1, scope=scope
    )
    player2_rank = await read_player_leaderboard_rank(
        session=session, player=player2, scope=scope
    )
    player1_nub = await get_pb_record_publics(
        session=session, map_id=None, map_name=None, stage=0,
        steamid64=player1.steamid64, scope=scope, record_type=RecordType.NUB,
        exclude_cheaters=True, limit=1_000_000,
    )
    player2_nub = await get_pb_record_publics(
        session=session, map_id=None, map_name=None, stage=0,
        steamid64=player2.steamid64, scope=scope, record_type=RecordType.NUB,
        exclude_cheaters=True, limit=1_000_000,
    )
    player1_pro = await get_pb_record_publics(
        session=session, map_id=None, map_name=None, stage=0,
        steamid64=player1.steamid64, scope=scope, record_type=RecordType.PRO,
        exclude_cheaters=True, limit=1_000_000,
    )
    player2_pro = await get_pb_record_publics(
        session=session, map_id=None, map_name=None, stage=0,
        steamid64=player2.steamid64, scope=scope, record_type=RecordType.PRO,
        exclude_cheaters=True, limit=1_000_000,
    )
    map_tiers = await _read_main_map_tiers(session=session, scope=scope)
    totals_by_tier: dict[int, int] = defaultdict(int)
    player1_by_tier: dict[int, int] = defaultdict(int)
    player2_by_tier: dict[int, int] = defaultdict(int)
    for tier in map_tiers.values():
        totals_by_tier[tier] += 1
    for map_id in {record.map_id for record in player1_nub}:
        map_tier = map_tiers.get(map_id)
        if map_tier is not None:
            player1_by_tier[map_tier] += 1
    for map_id in {record.map_id for record in player2_nub}:
        map_tier = map_tiers.get(map_id)
        if map_tier is not None:
            player2_by_tier[map_tier] += 1

    return PlayerComparisonPublic(
        scope=scope,
        player1=player1_rank,
        player2=player2_rank,
        progression=[
            PlayerCompareTierPublic(
                tier=tier,
                total_maps=totals_by_tier[tier],
                player1_finished=player1_by_tier[tier],
                player2_finished=player2_by_tier[tier],
            )
            for tier in range(1, 9)
        ],
        nub_runs=_build_run_rows(
            player1_records=player1_nub, player2_records=player2_nub
        ),
        pro_runs=_build_run_rows(
            player1_records=player1_pro, player2_records=player2_pro
        ),
    )
