import pytest
from sqlmodel import col, select

from app.core.config import settings
from app.crud.leaderboard_player import (
    _load_player_pb_rows,
    rebuild_leaderboard_player,
    rebuild_leaderboard_players_batch,
)
from app.crud.record import (
    _load_pro_preview_nub_finishers,
    rebuild_record_pb_points_bucket,
    rebuild_record_pb_points_for_course,
    recalculate_estimated_record_pb_points_for_player,
)
from app.models import LeaderboardPlayer, ModeScope, RecordPb, RecordType
from tests.api.routes.test_leaderboards import _seed_leaderboard_data


@pytest.mark.asyncio
async def test_selected_pro_bucket_persists_and_contributes_in_both_rating_builders(
    db, monkeypatch
):
    monkeypatch.setattr(settings, "LOCAL_OVR_NUB_RANK_POINTS_PREVIEW", True)
    monkeypatch.setattr(settings, "LOCAL_OVR_PRO_RANK_POINTS_PREVIEW", False)
    monkeypatch.setattr(settings, "LOCAL_OVR_PRO_POINTS_PREVIEW_COURSES", [])
    players = await _seed_leaderboard_data(db)
    player = players["alpha"]
    scope = ModeScope.OVR
    pb = (
        await db.exec(
            select(RecordPb).where(
                RecordPb.scope == scope,
                RecordPb.steamid64 == player,
                RecordPb.type == RecordType.PRO,
            )
        )
    ).one()
    course = pb.course_id
    assert pb.points == 1
    assert all(
        not row.record_type.is_pro
        for row in await _load_player_pb_rows(
            session=db, scope_id=scope.scope_id, steamid64=player
        )
    )
    before = (await db.get(LeaderboardPlayer, (scope, player))).points
    monkeypatch.setattr(settings, "LOCAL_OVR_PRO_POINTS_PREVIEW_COURSES", [course])
    assert (
        await _load_pro_preview_nub_finishers(
            session=db,
            course_id=course,
            scope_id=scope.scope_id,
            record_type=RecordType.PRO,
        )
        == 3
    )
    assert (
        await _load_pro_preview_nub_finishers(
            session=db,
            course_id=course,
            scope_id=scope.scope_id,
            record_type=RecordType.PRO,
            arriving_player=player,
        )
        == 3
    )
    assert (
        await rebuild_record_pb_points_bucket(
            session=db,
            course_id=course,
            scope_id=scope.scope_id,
            record_type=RecordType.PRO,
        )
        == 1
    )
    # Other buckets remain unchanged, and a regular course rebuild retains PRO.
    await rebuild_record_pb_points_for_course(
        session=db, course_id=course, scope_ids=[scope.scope_id]
    )
    current = (
        await db.exec(
            select(RecordPb).where(
                RecordPb.scope == scope,
                RecordPb.course_id == course,
                RecordPb.steamid64 == player,
                RecordPb.type == RecordType.PRO,
            )
        )
    ).one()
    assert current.points == 1000
    assert (
        await recalculate_estimated_record_pb_points_for_player(
            session=db, steamid64=player
        )
        == 0
    )
    await rebuild_leaderboard_players_batch(
        session=db, scope_id=scope.scope_id, steamid64s=[player]
    )
    row = await db.get(LeaderboardPlayer, (scope, player))
    assert row.points == before + 1000
    expected = row.model_dump(exclude={"updated_at"})
    await rebuild_leaderboard_player(
        session=db, scope_id=scope.scope_id, steamid64=player
    )
    assert row.model_dump(exclude={"updated_at"}) == expected
    assert (
        await db.exec(
            select(col(RecordPb.points)).where(
                RecordPb.scope == ModeScope.KZT,
                RecordPb.course_id == course,
                RecordPb.type == RecordType.PRO,
            )
        )
    ).one() == 1000
