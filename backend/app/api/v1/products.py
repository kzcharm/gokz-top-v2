from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentUser, SessionDep
from app.api.v1.player_api_helpers import (
    get_current_user_player_or_404,
    get_player_or_404,
)
from app.models.product import (
    GearLeaderboardPublic,
    ProductCategory,
    ProductCreate,
    ProductPublic,
    ProductsPublic,
    SetupInput,
    SetupPublic,
)
from app.services import products

router = APIRouter(tags=["products"])


@router.get("/products")
async def search_products(
    session: SessionDep,
    category: ProductCategory,
    q: Annotated[str, Query(max_length=301)] = "",
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ProductsPublic:
    return await products.list_products(session, category, q, skip, limit)


@router.get("/products/brands")
async def read_product_brands(
    session: SessionDep, category: ProductCategory
) -> list[str]:
    return await products.list_brands(session, category)


@router.post("/products")
async def create_product(
    session: SessionDep, current_user: CurrentUser, body: ProductCreate
) -> ProductPublic:
    player = await get_current_user_player_or_404(
        session=session, current_user=current_user
    )
    try:
        product = await products.create_product(session, body, player.steamid64)
        result = products.public_product(product)
        await session.commit()
        return result
    except PermissionError as exc:
        await session.rollback()
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@router.get("/me/setup")
async def read_my_setup(session: SessionDep, current_user: CurrentUser) -> SetupPublic:
    player = await get_current_user_player_or_404(
        session=session, current_user=current_user
    )
    return await products.read_setup(session, player.steamid64)


@router.put("/me/setup")
async def save_my_setup(
    session: SessionDep, current_user: CurrentUser, body: SetupInput
) -> SetupPublic:
    player = await get_current_user_player_or_404(
        session=session, current_user=current_user
    )
    try:
        result = await products.replace_setup(session, player.steamid64, body)
        await session.commit()
        return result
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/players/{identifier}/setup")
async def read_player_setup(session: SessionDep, identifier: str) -> SetupPublic:
    player = await get_player_or_404(session=session, identifier=identifier)
    return await products.read_setup(session, player.steamid64)


@router.get("/leaderboards/gear")
async def read_gear_leaderboard(
    session: SessionDep,
    category: ProductCategory = ProductCategory.MOUSE,
    q: Annotated[str, Query(max_length=301)] = "",
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> GearLeaderboardPublic:
    return await products.gear_leaderboard(session, category, q, skip, limit)
