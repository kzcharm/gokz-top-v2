from fastapi import APIRouter

from app.api.v1 import (
    admin_maps,
    admin_modes,
    admin_player_sessions,
    admin_player_social_links,
    admin_server_discovery,
    admin_servers,
    admin_tournaments,
    bans,
    graphql,
    jumpstats,
    leaderboards,
    live,
    login,
    maps,
    me_notifications,
    me_player_actions,
    me_qq_binding,
    me_settings,
    me_webhooks,
    media,
    misc,
    modes,
    player_follows,
    player_reports,
    player_sessions,
    player_social_links,
    player_ws,
    players,
    private,
    record_ws,
    records,
    regions,
    replays,
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
api_router.include_router(me_settings.router)
api_router.include_router(me_qq_binding.router)
api_router.include_router(me_webhooks.router)
api_router.include_router(me_player_actions.router)
api_router.include_router(me_notifications.router)
api_router.include_router(player_follows.router)
api_router.include_router(player_reports.router)
api_router.include_router(player_social_links.router)
api_router.include_router(player_social_links.verification_router)
api_router.include_router(graphql.router)
api_router.include_router(jumpstats.router)
api_router.include_router(leaderboards.router)
api_router.include_router(live.router)
api_router.include_router(media.router)
api_router.include_router(maps.router)
api_router.include_router(misc.router)
api_router.include_router(modes.router)
api_router.include_router(player_sessions.router)
api_router.include_router(player_ws.router)
api_router.include_router(records.router)
api_router.include_router(replays.router)
api_router.include_router(regions.router)
api_router.include_router(record_ws.router)
api_router.include_router(server_groups.router)
api_router.include_router(servers.router)
api_router.include_router(server_ws.router)
api_router.include_router(admin_maps.router)
api_router.include_router(admin_modes.router)
api_router.include_router(admin_player_sessions.router)
api_router.include_router(admin_player_social_links.router)
api_router.include_router(admin_tournaments.router)
api_router.include_router(admin_server_discovery.router)
api_router.include_router(admin_servers.router)
api_router.include_router(utils.router)


if settings.ENABLE_TEST_AUTH_HELPERS:
    api_router.include_router(private.router)
