from fastapi import APIRouter

from app.api.v0.maps import router as maps_router
from app.api.v0.modes import router as modes_router
from app.api.v0.servers import router as servers_router

router = APIRouter(prefix="/v0")
router.include_router(maps_router)
router.include_router(modes_router)
router.include_router(servers_router)
