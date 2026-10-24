from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app import crud
from app.api.deps import SessionDep, require_roles
from app.api.v1.player_api_helpers import get_player_or_404
from app.models import (
    Map,
    MapPronunciation,
    Player,
    PlayerPronunciation,
    User,
    UserRole,
)
from app.models.pronunciation import (
    PronunciationAdminPublic,
    PronunciationOptions,
    PronunciationRegenerate,
)
from app.services import pronunciation

router = APIRouter(prefix="/admin", tags=["pronunciations"])
PronunciationAdmin = Annotated[
    User, Depends(require_roles(UserRole.SUPERUSER, UserRole.ADMIN))
]
MapPronunciationAdmin = Annotated[
    User, Depends(require_roles(UserRole.SUPERUSER, UserRole.ADMIN, UserRole.MAP_ADMIN))
]


def ensure_configured() -> None:
    if not pronunciation.is_configured():
        raise HTTPException(status_code=503, detail="Pronunciation is unavailable")


async def get_options_or_503() -> PronunciationOptions:
    ensure_configured()
    try:
        return await pronunciation.get_options()
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="Voice and language choices are temporarily unavailable",
        ) from error


async def get_map(session: SessionDep, map_id: int) -> Map:
    target = await crud.get_map_by_id(session=session, id=map_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Map not found")
    return target


async def regenerate(
    session: SessionDep, target: Map | Player, payload: PronunciationRegenerate
) -> PronunciationAdminPublic:
    options = await get_options_or_503()
    try:
        await pronunciation.validate_overrides(payload, options)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    row = await pronunciation.request_pronunciation(
        session=session, target=target, overrides=payload
    )
    result = await pronunciation.admin_pronunciation(
        session=session, target=target, row=row
    )
    await session.commit()
    return result


@router.get("/pronunciations/options")
async def read_pronunciation_options(
    _user: MapPronunciationAdmin,
) -> PronunciationOptions:
    return await get_options_or_503()


@router.get("/maps/{map_id}/pronunciation")
async def read_admin_map_pronunciation(
    session: SessionDep, map_id: int, _user: MapPronunciationAdmin
) -> PronunciationAdminPublic:
    target = await get_map(session, map_id)
    ensure_configured()
    return await pronunciation.admin_pronunciation(
        session=session, target=target, row=await session.get(MapPronunciation, map_id)
    )


@router.post("/maps/{map_id}/pronunciation/regenerate", status_code=202)
async def regenerate_map_pronunciation(
    session: SessionDep,
    map_id: int,
    payload: PronunciationRegenerate,
    _user: MapPronunciationAdmin,
) -> PronunciationAdminPublic:
    return await regenerate(session, await get_map(session, map_id), payload)


@router.get("/players/{identifier}/pronunciation")
async def read_admin_player_pronunciation(
    session: SessionDep, identifier: str, _user: PronunciationAdmin
) -> PronunciationAdminPublic:
    target = await get_player_or_404(session=session, identifier=identifier)
    ensure_configured()
    return await pronunciation.admin_pronunciation(
        session=session,
        target=target,
        row=await session.get(PlayerPronunciation, target.steamid64),
    )


@router.post("/players/{identifier}/pronunciation/regenerate", status_code=202)
async def regenerate_player_pronunciation(
    session: SessionDep,
    identifier: str,
    payload: PronunciationRegenerate,
    _user: PronunciationAdmin,
) -> PronunciationAdminPublic:
    return await regenerate(
        session,
        await get_player_or_404(session=session, identifier=identifier),
        payload,
    )
