from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app import crud
from app.api.deps import (
    CurrentUser,
    OptionalCurrentUser,
    SessionDep,
    get_current_active_superuser,
    get_current_user,
)
from app.crud import player as player_crud
from app.models import (
    PlayerFollowListQuery,
    PlayerFollowSummaryPublic,
    PlayerPinnedRecordsPublic,
    PlayerPinnedRecordUpsert,
    PlayerProfileViewsPublic,
    PlayerPublic,
    PlayersBatchPublic,
    PlayersBatchRead,
    PlayerSearchQuery,
    PlayersListQuery,
    PlayersPublic,
    PlayerUpdate,
    RecordScope,
    RecordType,
    User,
)

router = APIRouter(prefix="/players", tags=["players"])
CurrentSuperuser = Annotated[User, Depends(get_current_active_superuser)]


def _parse_steamid64(steamid64: str) -> int:
    try:
        return int(steamid64)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid steamid64") from exc


async def _get_player_or_404(*, session: SessionDep, identifier: str):
    player = await player_crud.get_player_by_identifier(
        session=session,
        identifier=identifier,
    )
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return player


def _ensure_current_user_owns_player(
    *, current_user: CurrentUser, target_steamid64: int
) -> None:
    if current_user.steamid64 != target_steamid64:
        raise HTTPException(
            status_code=403,
            detail="You cannot modify another player's pinned records",
        )


@router.get("/", response_model=PlayersPublic)
async def read_players(
    session: SessionDep,
    query: Annotated[PlayersListQuery, Query()],
) -> Any:
    """
    Retrieve players.
    """
    players, count = await crud.read_players(
        session=session,
        offset=query.offset,
        limit=query.limit,
        sort_by=query.sort_by,
        sort_order=query.sort_order,
    )
    return PlayersPublic(
        data=await crud.to_player_publics(session=session, players=players),
        count=count,
    )


@router.get("/search", response_model=PlayersPublic)
async def search_players(
    session: SessionDep,
    query: Annotated[PlayerSearchQuery, Query()],
) -> PlayersPublic:
    """
    Search players by identifier, name, alias, and rating-weighted relevance.
    """
    players, count = await crud.search_players(
        session=session,
        q=query.q,
        offset=query.offset,
        limit=query.limit,
    )
    return PlayersPublic(
        data=await crud.to_player_publics(session=session, players=players),
        count=count,
    )


@router.post("/", response_model=PlayersBatchPublic)
async def read_players_batch(*, session: SessionDep, body: PlayersBatchRead) -> Any:
    """
    Retrieve players by steamid64 list.
    """
    steamid64s = [_parse_steamid64(steamid64) for steamid64 in body.steamid64s]
    players = await crud.read_players_batch(session=session, steamid64s=steamid64s)
    website_user_steamid64s = await crud.load_website_user_steamid64s(
        session=session,
        steamid64s=[player.steamid64 for player in players if player is not None],
    )
    data: list[PlayerPublic | None] = [
        (
            crud.to_player_public(
                player=player,
                is_website_user=player.steamid64 in website_user_steamid64s,
            )
            if player
            else None
        )
        for player in players
    ]
    return PlayersBatchPublic(data=data, count=len(data))


@router.post("/{identifier:path}/views", response_model=PlayerProfileViewsPublic)
async def create_player_view(
    identifier: str,
    session: SessionDep,
    current_user: CurrentUser,
) -> PlayerProfileViewsPublic:
    """
    Record an authenticated profile view for the current UTC day.
    """
    player = await _get_player_or_404(session=session, identifier=identifier)
    await crud.create_player_profile_view(
        session=session,
        viewer_steamid64=current_user.steamid64,
        target_steamid64=player.steamid64,
    )
    profile_views = await crud.count_player_profile_views(
        session=session,
        target_steamid64=player.steamid64,
    )
    return PlayerProfileViewsPublic(profile_views=profile_views)


@router.get(
    "/{identifier:path}/pinned-records",
    response_model=PlayerPinnedRecordsPublic,
)
async def read_player_pinned_records(
    identifier: str,
    session: SessionDep,
    scope: RecordScope = RecordScope.OVR,
) -> PlayerPinnedRecordsPublic:
    player = await _get_player_or_404(session=session, identifier=identifier)
    pinned_records = await crud.resolve_player_pinned_records_public(
        session=session,
        player_steamid64=player.steamid64,
        scope=scope,
    )
    return PlayerPinnedRecordsPublic(data=pinned_records, count=len(pinned_records))


@router.post(
    "/{identifier:path}/pinned-records",
    response_model=PlayerPinnedRecordsPublic,
)
async def create_player_pinned_record(
    identifier: str,
    body: PlayerPinnedRecordUpsert,
    session: SessionDep,
    current_user: CurrentUser,
) -> PlayerPinnedRecordsPublic:
    player = await _get_player_or_404(session=session, identifier=identifier)
    _ensure_current_user_owns_player(
        current_user=current_user,
        target_steamid64=player.steamid64,
    )

    records = await crud.get_pb_records(
        session,
        map_id=body.map_id,
        stage=0,
        steamid64=player.steamid64,
        scope=body.scope,
        record_type=body.type,
    )
    if len(records) == 0:
        raise HTTPException(status_code=404, detail="Pinned record target not found")

    await crud.create_player_pinned_record(
        session=session,
        player_steamid64=player.steamid64,
        map_id=body.map_id,
        scope=body.scope,
        record_type=body.type,
    )
    pinned_records = await crud.resolve_player_pinned_records_public(
        session=session,
        player_steamid64=player.steamid64,
        scope=body.scope,
    )
    return PlayerPinnedRecordsPublic(data=pinned_records, count=len(pinned_records))


@router.delete(
    "/{identifier:path}/pinned-records",
    response_model=PlayerPinnedRecordsPublic,
)
async def delete_player_pinned_record(
    identifier: str,
    session: SessionDep,
    current_user: CurrentUser,
    map_id: int,
    scope: RecordScope = RecordScope.OVR,
    type: RecordType = RecordType.NUB,
) -> PlayerPinnedRecordsPublic:
    player = await _get_player_or_404(session=session, identifier=identifier)
    _ensure_current_user_owns_player(
        current_user=current_user,
        target_steamid64=player.steamid64,
    )

    deleted = await crud.delete_player_pinned_record(
        session=session,
        player_steamid64=player.steamid64,
        map_id=map_id,
        scope=scope,
        record_type=type,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Pinned record not found")

    pinned_records = await crud.resolve_player_pinned_records_public(
        session=session,
        player_steamid64=player.steamid64,
        scope=scope,
    )
    return PlayerPinnedRecordsPublic(data=pinned_records, count=len(pinned_records))


@router.get(
    "/{identifier:path}/follow-summary", response_model=PlayerFollowSummaryPublic
)
async def read_player_follow_summary(
    identifier: str,
    session: SessionDep,
    current_user: OptionalCurrentUser,
) -> PlayerFollowSummaryPublic:
    """
    Retrieve follow counts and viewer relationship state for a player.
    """
    player = await _get_player_or_404(session=session, identifier=identifier)
    return await crud.get_player_follow_summary(
        session=session,
        target_steamid64=player.steamid64,
        viewer_steamid64=current_user.steamid64 if current_user else None,
    )


@router.post("/{identifier:path}/follow", response_model=PlayerFollowSummaryPublic)
async def follow_player(
    identifier: str,
    session: SessionDep,
    current_user: CurrentUser,
) -> PlayerFollowSummaryPublic:
    """
    Follow a player.
    """
    player = await _get_player_or_404(session=session, identifier=identifier)
    if current_user.steamid64 == player.steamid64:
        raise HTTPException(status_code=400, detail="You cannot follow yourself")

    await crud.create_player_follow(
        session=session,
        follower_steamid64=current_user.steamid64,
        followed_steamid64=player.steamid64,
    )
    return await crud.get_player_follow_summary(
        session=session,
        target_steamid64=player.steamid64,
        viewer_steamid64=current_user.steamid64,
    )


@router.delete("/{identifier:path}/follow", response_model=PlayerFollowSummaryPublic)
async def unfollow_player(
    identifier: str,
    session: SessionDep,
    current_user: CurrentUser,
) -> PlayerFollowSummaryPublic:
    """
    Unfollow a player.
    """
    player = await _get_player_or_404(session=session, identifier=identifier)
    if current_user.steamid64 == player.steamid64:
        raise HTTPException(status_code=400, detail="You cannot unfollow yourself")

    await crud.delete_player_follow(
        session=session,
        follower_steamid64=current_user.steamid64,
        followed_steamid64=player.steamid64,
    )
    return await crud.get_player_follow_summary(
        session=session,
        target_steamid64=player.steamid64,
        viewer_steamid64=current_user.steamid64,
    )


@router.get(
    "/{identifier:path}/followers",
    dependencies=[Depends(get_current_user)],
    response_model=PlayersPublic,
)
async def read_player_followers(
    identifier: str,
    session: SessionDep,
    query: Annotated[PlayerFollowListQuery, Query()],
) -> PlayersPublic:
    """
    Retrieve followers for a player.
    """
    player = await _get_player_or_404(session=session, identifier=identifier)
    followers, count = await crud.get_player_followers(
        session=session,
        target_steamid64=player.steamid64,
        offset=query.offset,
        limit=query.limit,
    )
    return PlayersPublic(
        data=await crud.to_player_publics(session=session, players=followers),
        count=count,
    )


@router.get(
    "/{identifier:path}/following",
    dependencies=[Depends(get_current_user)],
    response_model=PlayersPublic,
)
async def read_player_following(
    identifier: str,
    session: SessionDep,
    query: Annotated[PlayerFollowListQuery, Query()],
) -> PlayersPublic:
    """
    Retrieve players followed by a player.
    """
    player = await _get_player_or_404(session=session, identifier=identifier)
    following, count = await crud.get_player_following(
        session=session,
        target_steamid64=player.steamid64,
        offset=query.offset,
        limit=query.limit,
    )
    return PlayersPublic(
        data=await crud.to_player_publics(session=session, players=following),
        count=count,
    )


@router.get("/{identifier:path}", response_model=PlayerPublic)
async def read_player(identifier: str, session: SessionDep) -> Any:
    """
    Retrieve a player by app custom_id, steamid64, or full Steam profile URL.
    """
    player = await _get_player_or_404(session=session, identifier=identifier)
    return await crud.to_player_public_with_profile_views(session=session, player=player)


@router.put(
    "/{steamid64}/steam",
    dependencies=[Depends(get_current_user)],
    response_model=PlayerPublic,
)
async def upsert_player_from_steam(session: SessionDep, steamid64: str) -> Any:
    """
    Create or update player from Steam API.
    """
    parsed_steamid64 = _parse_steamid64(steamid64)
    player, _ = await crud.create_or_update_player_from_steam_if_fetched(
        session=session,
        steamid64=parsed_steamid64,
    )
    if player is None:
        existing_player = await crud.get_player_by_steamid64(
            session=session,
            steamid64=parsed_steamid64,
        )
        if existing_player is not None:
            return crud.to_player_public(player=existing_player)
        raise HTTPException(status_code=502, detail="Steam profile fetch failed")
    return crud.to_player_public(player=player)


@router.put(
    "/{steamid64}",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=PlayerPublic,
)
async def update_player(
    *,
    session: SessionDep,
    steamid64: str,
    player_in: PlayerUpdate,
    current_user: CurrentSuperuser,
) -> Any:
    """
    Update player profile data.
    """
    del current_user
    db_player = await crud.get_player_by_steamid64(
        session=session,
        steamid64=_parse_steamid64(steamid64),
    )
    if not db_player:
        raise HTTPException(status_code=404, detail="Player not found")

    updated_player = await crud.update_player(
        session=session,
        db_player=db_player,
        player_in=player_in,
    )
    return crud.to_player_public(player=updated_player)
