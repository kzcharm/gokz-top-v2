"""The maintenance batch must produce the same rows as live rebuilds."""

from datetime import timedelta

import pytest
from sqlalchemy import update
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.crud.leaderboard_player import (
    _load_player_pb_rows,
    rebuild_leaderboard_players_batch,
    rebuild_leaderboard_players_for_keys,
)
from app.models import LeaderboardPlayer, ModeScope, RecordPb, RecordType
from app.models.utils import get_datetime_utc
from app.services.daily_rank_pipeline_task import (
    DailyRankSelection,
    rebuild_daily_rank_leaderboards,
)
from tests.api.routes.test_leaderboards import _create_ban, _seed_leaderboard_data

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("ban_state", ["none", "active", "expired"])
@pytest.mark.parametrize("preview", [False, True])
@pytest.mark.parametrize("daily", [False, True])
async def test_batch_matches_live_rebuild_and_is_idempotent(
    db: AsyncSession,
    ban_state: str,
    preview: bool,
    daily: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    players = list((await _seed_leaderboard_data(db)).values())
    scope = ModeScope.OVR if preview else ModeScope.KZT
    monkeypatch.setattr(settings, "LOCAL_OVR_NUB_RANK_POINTS_PREVIEW", preview)
    monkeypatch.setattr(settings, "LOCAL_OVR_PRO_RANK_POINTS_PREVIEW", False)
    monkeypatch.setattr(settings, "LOCAL_OVR_PRO_POINTS_PREVIEW_COURSES", [])
    if preview:
        # Even stale high PRO scores must not affect the NUB-only preview.
        await db.exec(
            update(RecordPb)
            .where(RecordPb.scope == scope, RecordPb.type == RecordType.PRO)
            .values(points=999)
        )
        for player in players:
            assert all(
                row.record_type == RecordType.NUB
                for row in await _load_player_pb_rows(
                    session=db, scope_id=scope.scope_id, steamid64=player
                )
            )
    if ban_state != "none":
        await _create_ban(
            db,
            ban_id=2120900999,
            steamid64=players[0],
            expires_on=None
            if ban_state == "active"
            else get_datetime_utc() - timedelta(days=1),
        )
    await db.exec(update(LeaderboardPlayer).values(rating_easy=0, rating_hard=0))
    await db.exec(update(RecordPb).values(raw_rating_contribution=7))

    async def snapshot():
        leaders = (
            await db.exec(
                select(LeaderboardPlayer)
                .where(
                    col(LeaderboardPlayer.scope) == scope,
                    col(LeaderboardPlayer.steamid64).in_(players),
                )
                .order_by(col(LeaderboardPlayer.steamid64))
            )
        ).all()
        contributions = (
            await db.exec(
                select(
                    col(RecordPb.steamid64),
                    col(RecordPb.course_id),
                    col(RecordPb.type),
                    col(RecordPb.raw_rating_contribution),
                )
                .where(
                    col(RecordPb.scope) == scope,
                    col(RecordPb.steamid64).in_(players),
                )
                .order_by(
                    col(RecordPb.steamid64), col(RecordPb.course_id), col(RecordPb.type)
                )
            )
        ).all()
        return (
            [row.model_dump(exclude={"updated_at"}) for row in leaders],
            list(contributions),
        )

    savepoint = await db.begin_nested()
    old_result = await rebuild_leaderboard_players_for_keys(
        session=db,
        keys=[(scope.scope_id, player) for player in players],
    )
    await db.flush()
    expected = await snapshot()
    if preview:
        assert all(
            value == 0 for _, _, kind, value in expected[1] if kind == RecordType.PRO
        )
    await savepoint.rollback()
    if daily:
        now = get_datetime_utc()
        result = await rebuild_daily_rank_leaderboards(
            session=db,
            selection=DailyRankSelection(
                window_start=now - timedelta(days=1),
                window_end=now,
                pb_row_count=0,
                point_buckets=[],
                leaderboard_keys=[(scope.scope_id, player) for player in players],
                map_leaderboard_keys=[],
                map_stat_keys=[],
                steamid64s=players,
            ),
        )
    else:
        result = await rebuild_leaderboard_players_batch(
            session=db,
            scope_id=scope.scope_id,
            steamid64s=players,
        )
    assert result == old_result
    assert await snapshot() == expected
    assert await rebuild_leaderboard_players_batch(
        session=db,
        scope_id=scope.scope_id,
        steamid64s=players,
    ) == (0, 0)
    assert await rebuild_leaderboard_players_batch(
        session=db,
        scope_id=scope.scope_id,
        steamid64s=[],
    ) == (0, 0)
