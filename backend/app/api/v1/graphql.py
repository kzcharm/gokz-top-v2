from __future__ import annotations

from datetime import datetime
from typing import Annotated

import strawberry
from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession
from strawberry.fastapi import GraphQLRouter

from app.api.deps import get_db
from app.crud import player as player_crud
from app.crud.leaderboard_player import load_player_ratings_by_scope
from app.crud.player_profile_view import count_player_profile_views_batch
from app.models import ModeScope, Player
from app.models.leaderboard_player import scale_public_rating

strawberry.enum(ModeScope, name="ModeScope")


@strawberry.type
class PlayerGQL:
    steamid64: strawberry.ID
    display_name: str
    name: str
    alias: str | None
    custom_id: str | None
    avatar_hash: str | None
    country: str | None
    primary_scope: ModeScope
    is_website_user: bool
    last_played_at: str | None
    created_at: str | None
    updated_at: str | None
    profile_views: int
    ratings_by_scope: strawberry.Private[dict[ModeScope, int]]

    @strawberry.field
    def rating(self, scope: ModeScope | None = None) -> float:
        effective_scope = scope or self.primary_scope
        raw_rating = self.ratings_by_scope.get(effective_scope, 0)
        return scale_public_rating(raw_rating) or 0


@strawberry.type
class PlayerConnectionGQL:
    data: list[PlayerGQL]
    count: int


def _serialize_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _get_session(info: strawberry.Info[dict[str, AsyncSession], None]) -> AsyncSession:
    return info.context["session"]


async def _to_graphql_players(
    *,
    session: AsyncSession,
    players: list[Player | None],
) -> list[PlayerGQL | None]:
    existing_players = [player for player in players if player is not None]
    if not existing_players:
        return [None for _player in players]

    steamid64s = [player.steamid64 for player in existing_players]
    website_user_steamid64s = await player_crud.load_website_user_steamid64s(
        session=session,
        steamid64s=steamid64s,
    )
    profile_views_by_steamid64 = await count_player_profile_views_batch(
        session=session,
        target_steamid64s=steamid64s,
    )
    ratings_by_steamid64 = await load_player_ratings_by_scope(
        session=session,
        steamid64s=steamid64s,
    )

    graphql_players_by_steamid64 = {
        player.steamid64: PlayerGQL(
            steamid64=strawberry.ID(str(player.steamid64)),
            display_name=player_crud.get_player_display_name(player=player),
            name=player.name,
            alias=player.alias,
            custom_id=player_crud.normalize_custom_id(player.custom_id),
            avatar_hash=player.avatar_hash,
            country=player.country,
            primary_scope=player.primary_scope,
            is_website_user=player.steamid64 in website_user_steamid64s,
            last_played_at=_serialize_datetime(player.last_played_at),
            created_at=_serialize_datetime(player.created_at),
            updated_at=_serialize_datetime(player.updated_at),
            profile_views=profile_views_by_steamid64.get(player.steamid64, 0),
            ratings_by_scope=ratings_by_steamid64.get(player.steamid64, {}),
        )
        for player in existing_players
    }
    return [
        graphql_players_by_steamid64.get(player.steamid64) if player is not None else None
        for player in players
    ]


@strawberry.type
class Query:
    @strawberry.field
    async def player(
        self,
        info: strawberry.Info[dict[str, AsyncSession], None],
        identifier: str,
    ) -> PlayerGQL | None:
        player = await player_crud.get_player_by_identifier(
            session=_get_session(info),
            identifier=identifier,
        )
        graphql_players = await _to_graphql_players(
            session=_get_session(info),
            players=[player],
        )
        return graphql_players[0]

    @strawberry.field
    async def players(
        self,
        info: strawberry.Info[dict[str, AsyncSession], None],
        steamid64s: list[strawberry.ID],
    ) -> list[PlayerGQL | None]:
        parsed_steamid64s: list[int | None] = []
        valid_steamid64s: list[int] = []
        for steamid64 in steamid64s:
            try:
                parsed = int(str(steamid64))
            except ValueError:
                parsed_steamid64s.append(None)
                continue
            parsed_steamid64s.append(parsed)
            valid_steamid64s.append(parsed)

        players_by_steamid64 = {
            player.steamid64: player
            for player in await player_crud.read_players_batch(
                session=_get_session(info),
                steamid64s=valid_steamid64s,
            )
            if player is not None
        }
        ordered_players = [
            players_by_steamid64.get(parsed_steamid64)
            if parsed_steamid64 is not None
            else None
            for parsed_steamid64 in parsed_steamid64s
        ]
        return await _to_graphql_players(
            session=_get_session(info),
            players=ordered_players,
        )

    @strawberry.field
    async def search_players(
        self,
        info: strawberry.Info[dict[str, AsyncSession], None],
        q: str,
        offset: int = 0,
        limit: int = 20,
    ) -> PlayerConnectionGQL:
        players, count = await player_crud.search_players(
            session=_get_session(info),
            q=q,
            offset=offset,
            limit=limit,
        )
        graphql_players = await _to_graphql_players(
            session=_get_session(info),
            players=list(players),
        )
        return PlayerConnectionGQL(
            data=[player for player in graphql_players if player is not None],
            count=count,
        )


async def get_graphql_context(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, AsyncSession]:
    return {"session": session}


schema = strawberry.Schema(query=Query)
router = GraphQLRouter(
    schema,
    path="/graphql",
    context_getter=get_graphql_context,
)
