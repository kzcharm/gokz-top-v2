from fastapi import APIRouter

from app.api.v1 import (
    admin_modes,
    items,
    login,
    modes,
    players,
    private,
    users,
    utils,
)
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(players.router)
api_router.include_router(modes.router)
api_router.include_router(admin_modes.router)
api_router.include_router(utils.router)
api_router.include_router(items.router)


if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
