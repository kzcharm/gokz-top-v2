from fastapi import APIRouter

from app.api.v1 import (
    admin_maps,
    admin_modes,
    admin_player_sessions,
    admin_player_social_links,
    admin_servers,
    bans,
    graphql,
    jumpstats,
    leaderboards,
    live,
    login,
    maps,
    modes,
    player_sessions,
    players,
    private,
    record_ws,
    records,
    regions,
    server_groups,
    server_ws,
    servers,
    users,
    utils,
)
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(bans.router)
api_router.include_router(players.router)
api_router.include_router(graphql.router)
api_router.include_router(jumpstats.router)
api_router.include_router(leaderboards.router)
api_router.include_router(live.router)
api_router.include_router(maps.router)
api_router.include_router(modes.router)
api_router.include_router(player_sessions.router)
api_router.include_router(records.router)
api_router.include_router(regions.router)
api_router.include_router(record_ws.router)
api_router.include_router(server_groups.router)
api_router.include_router(servers.router)
api_router.include_router(server_ws.router)
api_router.include_router(admin_maps.router)
api_router.include_router(admin_modes.router)
api_router.include_router(admin_player_sessions.router)
api_router.include_router(admin_player_social_links.router)
api_router.include_router(admin_servers.router)
api_router.include_router(utils.router)


if settings.ENABLE_TEST_AUTH_HELPERS:
    api_router.include_router(private.router)
