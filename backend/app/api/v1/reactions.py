import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app import crud
from app.api.deps import CurrentUser, SessionDep
from app.models import (
    ReactionCreate,
    ReactionEmojiPublic,
    ReactionSummaryPublic,
    ReactionTargetType,
    ReactionUsersPublic,
)

router = APIRouter(prefix="/reactions", tags=["reactions"])


@router.get("/emojis", response_model=list[ReactionEmojiPublic])
async def read_reaction_emojis() -> list[ReactionEmojiPublic]:
    return list(crud.REACTION_EMOJIS)


@router.put("/{target_type}/{target_id}", response_model=ReactionSummaryPublic)
async def put_reaction(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    target_type: ReactionTargetType,
    target_id: str,
    body: ReactionCreate,
) -> ReactionSummaryPublic:
    try:
        parsed_target_id = crud.parse_reaction_target_id(target_type, target_id)
        return await crud.create_content_reaction(
            session=session,
            target_type=target_type,
            target_id=parsed_target_id,
            user_steamid64=current_user.steamid64,
            emoji_key=body.emoji_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{reaction_id}", response_model=ReactionSummaryPublic)
async def delete_reaction(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    reaction_id: uuid.UUID,
) -> ReactionSummaryPublic:
    try:
        target_type, target_id = await crud.delete_content_reaction(
            session=session,
            reaction_id=reaction_id,
            user_steamid64=current_user.steamid64,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return (
        await crud.load_reaction_summaries(
            session=session,
            target_type=target_type,
            target_ids=[target_id],
            viewer_steamid64=current_user.steamid64,
        )
    )[target_id]


@router.get("/{target_type}/{target_id}/reactors", response_model=ReactionUsersPublic)
async def read_reactors(
    *,
    session: SessionDep,
    target_type: ReactionTargetType,
    target_id: str,
    emoji_key: Annotated[str, Query(min_length=1, max_length=128)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ReactionUsersPublic:
    try:
        parsed_target_id = crud.parse_reaction_target_id(target_type, target_id)
        return await crud.read_reaction_users(
            session=session,
            target_type=target_type,
            target_id=parsed_target_id,
            emoji_key=emoji_key,
            offset=offset,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
