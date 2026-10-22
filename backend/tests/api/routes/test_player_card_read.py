from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import BackgroundTasks

from app.api.v1 import players
from app.models import Player


@pytest.mark.asyncio
@pytest.mark.parametrize("refresh", [True, False])
async def test_player_card_read_can_skip_steam_refresh(refresh: bool) -> None:
    player = Player(
        steamid64=76561198000000001,
        name="Card player",
        created_at=datetime(2022, 1, 1, tzinfo=UTC),
    )
    tasks = BackgroundTasks()
    with (
        patch.object(players, "get_player_or_404", AsyncMock(return_value=player)),
        patch.object(players, "is_player_steam_profile_sync_due", return_value=True),
        patch.object(
            players.crud, "load_player_roles_by_steamid64", AsyncMock(return_value={})
        ),
        patch.object(
            players.crud,
            "resolve_player_favorite_server_public",
            AsyncMock(return_value=None),
        ),
    ):
        result = await players.read_player(
            identifier=str(player.steamid64),
            session=AsyncMock(),
            background_tasks=tasks,
            refresh_steam_profile=refresh,
        )
    assert result.name == "Card player"
    assert len(tasks.tasks) == (1 if refresh else 0)
