import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from app import crud
from app.api.deps import (
    CurrentUser,
    OptionalCurrentUser,
    SessionDep,
    get_current_active_superuser,
    get_current_user,
    user_has_role,
)
from app.api.v1.player_api_helpers import (
    drop_null_group_ids,
    ensure_current_user_can_manage_player_comment,
    get_current_user_player_or_404,
    get_player_or_404,
    parse_steamid64,
    resolve_player_identifier_to_steamid64_or_404,
)
from app.models import (
    JumpstatListQuery,
    JumpstatsPublic,
    Message,
    ModeScope,
    PlayerCommentCreate,
    PlayerCommentListQuery,
    PlayerCommentPublic,
    PlayerCommentsPublic,
    PlayerDailyActivityPublic,
    PlayerDetailPublic,
    PlayerFollowListQuery,
    PlayerFriendsPublic,
    PlayerLikerPublic,
    PlayerLikersPublic,
    PlayerLikesPublic,
    PlayerMostPlayedServerPublic,
    PlayerPinnedRecordsPublic,
    PlayerPlaytimePublic,
    PlayerProfileHistoryListQuery,
    PlayerProfileHistoryPublic,
    PlayerProfileViewsPublic,
    PlayerPublic,
    PlayersBatchPublic,
    PlayersBatchRead,
    PlayerSearchQuery,
    PlayersListQuery,
    PlayersPublic,
    PlayerStatsPublic,
    PlayerStatType,
    PlayerUpdate,
    User,
    UserRole,
)
from app.services.player_friends import read_player_friends_public
from app.services.player_steam_profile import (
    is_player_steam_profile_sync_due,
    sync_player_steam_profile_if_due,
)

router = APIRouter(prefix="/players", tags=["players"])
CurrentSuperuser = Annotated[User, Depends(get_current_active_superuser)]


@router.get("", response_model=PlayersPublic)
async def read_players(
    session: SessionDep,
    query: Annotated[PlayersListQuery, Query()],
) -> Any:
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


@router.post("", response_model=PlayersBatchPublic)
async def read_players_batch(*, session: SessionDep, body: PlayersBatchRead) -> Any:
    steamid64s = [parse_steamid64(steamid64) for steamid64 in body.steamid64s]
    players = await crud.read_players_batch(session=session, steamid64s=steamid64s)
    roles_by_steamid64 = await crud.load_player_roles_by_steamid64(
        session=session,
        steamid64s=[player.steamid64 for player in players if player is not None],
    )
    data: list[PlayerPublic | None] = [
        (
            crud.to_player_public(
                player=player,
                roles=roles_by_steamid64.get(player.steamid64),
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
    player = await get_player_or_404(session=session, identifier=identifier)
    if not user_has_role(current_user, UserRole.SUPERUSER):
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


@router.post("/{identifier:path}/likes", response_model=PlayerLikesPublic)
async def create_player_like(
    identifier: str,
    session: SessionDep,
    current_user: CurrentUser,
) -> PlayerLikesPublic:
    player = await get_player_or_404(session=session, identifier=identifier)
    created = await crud.create_player_like(
        session=session,
        viewer_steamid64=current_user.steamid64,
        target_steamid64=player.steamid64,
    )
    player_likes = await crud.count_player_likes(
        session=session,
        target_steamid64=player.steamid64,
    )
    return PlayerLikesPublic(player_likes=player_likes, created=created)


@router.get("/{identifier:path}/views", response_model=PlayerProfileViewsPublic)
async def read_player_views(
    identifier: str,
    session: SessionDep,
) -> PlayerProfileViewsPublic:
    player = await get_player_or_404(session=session, identifier=identifier)
    profile_views = await crud.count_player_profile_views(
        session=session,
        target_steamid64=player.steamid64,
    )
    return PlayerProfileViewsPublic(profile_views=profile_views)


@router.get("/{identifier:path}/comments", response_model=PlayerCommentsPublic)
async def read_player_comments(
    *,
    identifier: str,
    session: SessionDep,
    query: Annotated[PlayerCommentListQuery, Query()],
) -> PlayerCommentsPublic:
    player = await get_player_or_404(session=session, identifier=identifier)
    rows, count = await crud.read_player_comments(
        session=session,
        target_steamid64=player.steamid64,
        offset=query.offset,
        limit=query.limit,
    )
    return PlayerCommentsPublic(
        data=[
            crud.to_player_comment_public(comment=comment, author=author)
            for comment, author in rows
        ],
        count=count,
    )


@router.post("/{identifier:path}/comments", response_model=PlayerCommentPublic)
async def create_player_comment(
    *,
    identifier: str,
    session: SessionDep,
    payload: PlayerCommentCreate,
    current_user: CurrentUser,
):
    target_player = await get_player_or_404(session=session, identifier=identifier)
    author_player = await get_current_user_player_or_404(
        session=session,
        current_user=current_user,
    )
    if author_player.steamid64 == target_player.steamid64:
        raise HTTPException(
            status_code=400,
            detail="You cannot comment on your own profile",
        )

    comment = await crud.create_player_comment(
        session=session,
        author_steamid64=author_player.steamid64,
        target_steamid64=target_player.steamid64,
        text=payload.text,
    )
    return crud.to_player_comment_public(comment=comment, author=author_player)


@router.delete("/{identifier:path}/comments/{comment_id}", response_model=Message)
async def delete_player_comment(
    *,
    identifier: str,
    comment_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> Message:
    player = await get_player_or_404(session=session, identifier=identifier)
    comment = await crud.get_player_comment(session=session, id=comment_id)
    if comment is None or comment.target_steamid64 != player.steamid64:
        raise HTTPException(status_code=404, detail="Player comment not found")

    ensure_current_user_can_manage_player_comment(
        current_user=current_user,
        author_steamid64=comment.author_steamid64,
        target_steamid64=comment.target_steamid64,
    )
    await crud.delete_player_comment(session=session, comment=comment)
    return Message(message="Player comment deleted")


@router.get("/{identifier:path}/likes", response_model=PlayerLikesPublic)
async def read_player_likes(
    identifier: str,
    session: SessionDep,
) -> PlayerLikesPublic:
    player = await get_player_or_404(session=session, identifier=identifier)
    player_likes = await crud.count_player_likes(
        session=session,
        target_steamid64=player.steamid64,
    )
    return PlayerLikesPublic(player_likes=player_likes)


@router.get(
    "/{identifier:path}/likes/players",
    dependencies=[Depends(get_current_user)],
    response_model=PlayerLikersPublic,
)
async def read_player_likers(
    identifier: str,
    session: SessionDep,
    query: Annotated[PlayerFollowListQuery, Query()],
) -> PlayerLikersPublic:
    player = await get_player_or_404(session=session, identifier=identifier)
    liker_rows, count = await crud.get_player_likers(
        session=session,
        target_steamid64=player.steamid64,
        offset=query.offset,
        limit=query.limit,
    )
    liker_players = [liker for liker, _latest_like_at in liker_rows]
    public_likers = await crud.to_player_publics(session=session, players=liker_players)
    return PlayerLikersPublic(
        data=[
            PlayerLikerPublic(
                **public_liker.model_dump(),
                latest_like_at=latest_like_at,
            )
            for public_liker, (_liker, latest_like_at) in zip(
                public_likers,
                liker_rows,
                strict=True,
            )
        ],
        count=count,
    )


@router.get("/{identifier:path}/pinned-records", response_model=PlayerPinnedRecordsPublic)
async def read_player_pinned_records(
    identifier: str,
    session: SessionDep,
    scope: ModeScope = ModeScope.OVR,
) -> PlayerPinnedRecordsPublic:
    player = await get_player_or_404(session=session, identifier=identifier)
    pinned_records = await crud.resolve_player_pinned_records_public(
        session=session,
        player_steamid64=player.steamid64,
        scope=scope,
    )
    return PlayerPinnedRecordsPublic(data=pinned_records, count=len(pinned_records))


@router.get(
    "/{identifier:path}/stats",
    response_model=PlayerStatsPublic,
    response_model_exclude_none=False,
)
async def read_player_stats(
    identifier: str,
    session: SessionDep,
    type: Annotated[PlayerStatType | None, Query()] = None,
) -> JSONResponse:
    player = await get_player_or_404(session=session, identifier=identifier)
    if type is not None:
        if type == PlayerStatType.DAILY_ACTIVITY:
            daily_activity = await crud.get_or_rebuild_player_daily_activity_stat(
                session=session,
                steamid64=player.steamid64,
            )
            payload = PlayerDailyActivityPublic(
                updated_at=daily_activity.updated_at,
                **daily_activity.content.model_dump(mode="json"),
            )
        elif type == PlayerStatType.PLAYTIME:
            playtime = await crud.get_or_rebuild_player_playtime_stat(
                session=session,
                steamid64=player.steamid64,
            )
            payload = PlayerPlaytimePublic(
                updated_at=playtime.updated_at,
                **playtime.content.model_dump(mode="json"),
            )
        else:
            most_played_server = await crud.get_or_rebuild_player_most_played_server_stat(
                session=session,
                steamid64=player.steamid64,
            )
            payload = PlayerMostPlayedServerPublic(
                updated_at=most_played_server.updated_at,
                **most_played_server.content.model_dump(mode="json"),
            )
        response_payload = {
            "steamid64": str(player.steamid64),
            type.value: payload.model_dump(mode="json"),
        }
        drop_null_group_ids(response_payload)
        return JSONResponse(content=response_payload)

    stats = await crud.get_or_rebuild_player_stats(
        session=session,
        steamid64=player.steamid64,
        stat_type=type,
    )
    response_payload = stats.model_dump(mode="json")
    drop_null_group_ids(response_payload)
    return JSONResponse(content=response_payload)


@router.get("/{identifier:path}/jumpstats", response_model=JumpstatsPublic)
async def read_player_jumpstats(
    identifier: str,
    session: SessionDep,
    query: Annotated[JumpstatListQuery, Query()],
) -> JumpstatsPublic:
    player_steamid64 = await resolve_player_identifier_to_steamid64_or_404(
        session=session,
        identifier=identifier,
    )
    rows, count = await crud.read_jumpstats(
        session=session,
        query=query,
        player_steamid64=player_steamid64,
    )
    return JumpstatsPublic(data=crud.to_jumpstat_publics(rows=rows), count=count)


@router.get("/{identifier:path}/friends", response_model=PlayerFriendsPublic)
async def read_player_friends(
    identifier: str,
    session: SessionDep,
    current_user: OptionalCurrentUser,
) -> PlayerFriendsPublic:
    del current_user
    player = await get_player_or_404(session=session, identifier=identifier)
    return await read_player_friends_public(session=session, player=player)


@router.get(
    "/{identifier:path}/profile-history",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=PlayerProfileHistoryPublic,
)
async def read_player_profile_history(
    *,
    session: SessionDep,
    identifier: str,
    query: Annotated[PlayerProfileHistoryListQuery, Query()],
    current_user: CurrentSuperuser,
) -> PlayerProfileHistoryPublic:
    del current_user
    player_steamid64 = await resolve_player_identifier_to_steamid64_or_404(
        session=session,
        identifier=identifier,
    )
    rows, count = await crud.read_player_profile_history(
        session=session,
        player_steamid64=player_steamid64,
        offset=query.offset,
        limit=query.limit,
    )
    return PlayerProfileHistoryPublic(
        data=crud.to_player_profile_history_publics(histories=rows),
        count=count,
    )


@router.get("/{identifier:path}", response_model=PlayerDetailPublic)
async def read_player(
    identifier: str,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> PlayerDetailPublic:
    player = await get_player_or_404(session=session, identifier=identifier)
    if is_player_steam_profile_sync_due(player=player, now=datetime.now(UTC)):
        background_tasks.add_task(
            sync_player_steam_profile_if_due,
            steamid64=player.steamid64,
        )
    roles_by_steamid64 = await crud.load_player_roles_by_steamid64(
        session=session,
        steamid64s=[player.steamid64],
    )
    return crud.to_player_detail_public(
        player=player,
        roles=roles_by_steamid64.get(player.steamid64),
    )


@router.put(
    "/{identifier:path}/steam",
    response_model=PlayerPublic,
)
async def upsert_player_from_steam(
    session: SessionDep,
    identifier: str,
    current_user: CurrentUser,
) -> Any:
    del current_user
    parsed_steamid64 = await resolve_player_identifier_to_steamid64_or_404(
        session=session,
        identifier=identifier,
    )
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


@router.put("/{identifier:path}", response_model=PlayerPublic)
async def update_player(
    *,
    session: SessionDep,
    identifier: str,
    player_in: PlayerUpdate,
    current_user: CurrentSuperuser,
) -> Any:
    del current_user
    db_player = await crud.get_player_by_steamid64(
        session=session,
        steamid64=await resolve_player_identifier_to_steamid64_or_404(
            session=session,
            identifier=identifier,
        ),
    )
    if not db_player:
        raise HTTPException(status_code=404, detail="Player not found")

    updated_player = await crud.update_player(
        session=session,
        db_player=db_player,
        player_in=player_in,
    )
    return crud.to_player_public(player=updated_player)
