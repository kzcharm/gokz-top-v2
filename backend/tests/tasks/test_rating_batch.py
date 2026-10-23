"""The maintenance batch must produce the same rows as live rebuilds."""

from datetime import timedelta

import pytest
from sqlalchemy import update
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.crud.leaderboard_player import (
    rebuild_leaderboard_players_batch,
    rebuild_leaderboard_players_for_keys,
)
from app.models import LeaderboardPlayer, ModeScope, RecordPb
from app.models.utils import get_datetime_utc
from tests.api.routes.test_leaderboards import _create_ban, _seed_leaderboard_data

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("ban_state", ["none", "active", "expired"])
async def test_batch_matches_live_rebuild_and_is_idempotent(
    db: AsyncSession, ban_state: str
) -> None:
    players = list((await _seed_leaderboard_data(db)).values())
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
                    col(LeaderboardPlayer.scope) == ModeScope.KZT,
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
                    col(RecordPb.scope) == ModeScope.KZT,
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
        keys=[(1, player) for player in players],
    )
    await db.flush()
    expected = await snapshot()
    await savepoint.rollback()
    result = await rebuild_leaderboard_players_batch(
        session=db,
        scope_id=1,
        steamid64s=players,
    )
    assert result == old_result
    assert await snapshot() == expected
    assert await rebuild_leaderboard_players_batch(
        session=db,
        scope_id=1,
        steamid64s=players,
    ) == (0, 0)
    assert await rebuild_leaderboard_players_batch(
        session=db,
        scope_id=1,
        steamid64s=[],
    ) == (0, 0)
