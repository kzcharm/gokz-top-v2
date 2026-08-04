import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app import crud
from app.api.deps import SessionDep, get_current_active_superuser
from app.models import (
    AdminTournamentAchievementPublic,
    AdminTournamentAchievementsPublic,
    TournamentAchievementCreate,
    TournamentAchievementUpdate,
    TournamentCreate,
    TournamentListQuery,
    TournamentPublic,
    TournamentsPublic,
    TournamentUpdate,
    User,
)

router = APIRouter(prefix="/admin/tournaments", tags=["admin-tournaments"])
CurrentSuperuser = Annotated[User, Depends(get_current_active_superuser)]


def _parse_steamid64(value: str) -> int:
    normalized = value.strip()
    if not normalized.isdigit():
        raise HTTPException(status_code=422, detail="steamid64 must be numeric")
    return int(normalized)


@router.get("", response_model=TournamentsPublic)
async def read_admin_tournaments(
    *,
    session: SessionDep,
    query: Annotated[TournamentListQuery, Query()],
    _current_user: CurrentSuperuser,
) -> TournamentsPublic:
    tournaments, count = await crud.read_tournaments(
        session=session, offset=query.offset, limit=query.limit
    )
    return TournamentsPublic(
        data=[
            crud.to_tournament_public(tournament=tournament)
            for tournament in tournaments
        ],
        count=count,
    )


@router.post("", response_model=TournamentPublic)
async def create_admin_tournament(
    *,
    session: SessionDep,
    tournament_in: TournamentCreate,
    _current_user: CurrentSuperuser,
) -> TournamentPublic:
    tournament = await crud.create_tournament(
        session=session, tournament_in=tournament_in
    )
    return crud.to_tournament_public(tournament=tournament)


@router.patch("/{tournament_id}", response_model=TournamentPublic)
async def update_admin_tournament(
    *,
    session: SessionDep,
    tournament_id: uuid.UUID,
    tournament_in: TournamentUpdate,
    _current_user: CurrentSuperuser,
) -> TournamentPublic:
    tournament = await crud.get_tournament(session=session, id=tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    try:
        tournament = await crud.update_tournament(
            session=session, tournament=tournament, tournament_in=tournament_in
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return crud.to_tournament_public(tournament=tournament)


@router.delete("/{tournament_id}")
async def delete_admin_tournament(
    *,
    session: SessionDep,
    tournament_id: uuid.UUID,
    _current_user: CurrentSuperuser,
) -> dict[str, str]:
    tournament = await crud.get_tournament(session=session, id=tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    await crud.delete_tournament(session=session, tournament=tournament)
    return {"message": "Tournament deleted successfully"}


@router.get("/achievements", response_model=AdminTournamentAchievementsPublic)
async def read_admin_tournament_achievements(
    *,
    session: SessionDep,
    query: Annotated[TournamentListQuery, Query()],
    _current_user: CurrentSuperuser,
) -> AdminTournamentAchievementsPublic:
    rows, count = await crud.read_admin_tournament_achievements(
        session=session, offset=query.offset, limit=query.limit
    )
    return AdminTournamentAchievementsPublic(
        data=[
            crud.to_admin_tournament_achievement_public(
                achievement=achievement, tournament=tournament, player=player
            )
            for achievement, tournament, player in rows
        ],
        count=count,
    )


@router.post("/achievements", response_model=AdminTournamentAchievementPublic)
async def create_admin_tournament_achievement(
    *,
    session: SessionDep,
    achievement_in: TournamentAchievementCreate,
    _current_user: CurrentSuperuser,
) -> AdminTournamentAchievementPublic:
    tournament = await crud.get_tournament(
        session=session, id=achievement_in.tournament_id
    )
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    player_steamid64 = _parse_steamid64(achievement_in.player_steamid64)
    player = await crud.get_player_by_steamid64(
        session=session, steamid64=player_steamid64
    )
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    try:
        achievement = await crud.create_tournament_achievement(
            session=session,
            tournament_id=tournament.id,
            player_steamid64=player.steamid64,
            placement=achievement_in.placement,
        )
    except crud.TournamentAchievementConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return crud.to_admin_tournament_achievement_public(
        achievement=achievement, tournament=tournament, player=player
    )


@router.patch(
    "/achievements/{achievement_id}", response_model=AdminTournamentAchievementPublic
)
async def update_admin_tournament_achievement(
    *,
    session: SessionDep,
    achievement_id: uuid.UUID,
    achievement_in: TournamentAchievementUpdate,
    _current_user: CurrentSuperuser,
) -> AdminTournamentAchievementPublic:
    achievement = await crud.get_tournament_achievement(
        session=session, id=achievement_id
    )
    if achievement is None:
        raise HTTPException(status_code=404, detail="Tournament achievement not found")
    tournament = await crud.get_tournament(
        session=session, id=achievement.tournament_id
    )
    player = await crud.get_player_by_steamid64(
        session=session, steamid64=achievement.player_steamid64
    )
    if tournament is None or player is None:
        raise HTTPException(status_code=404, detail="Tournament achievement not found")
    achievement = await crud.update_tournament_achievement(
        session=session, achievement=achievement, placement=achievement_in.placement
    )
    return crud.to_admin_tournament_achievement_public(
        achievement=achievement, tournament=tournament, player=player
    )


@router.delete("/achievements/{achievement_id}")
async def delete_admin_tournament_achievement(
    *,
    session: SessionDep,
    achievement_id: uuid.UUID,
    _current_user: CurrentSuperuser,
) -> dict[str, str]:
    achievement = await crud.get_tournament_achievement(
        session=session, id=achievement_id
    )
    if achievement is None:
        raise HTTPException(status_code=404, detail="Tournament achievement not found")
    await crud.delete_tournament_achievement(session=session, achievement=achievement)
    return {"message": "Tournament achievement deleted successfully"}
