import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any

import sentry_sdk
from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.openapi.docs import swagger_ui_default_parameters
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware

from app.api.main import api_router
from app.api.v0.main import router as v0_router
from app.api.v1.misc import router as misc_router
from app.core.config import settings
from app.core.logging import configure_app_logging
from app.services.daily_rank_pipeline_task import (
    run_daily_rank_pipeline_runner_in_app,
    stop_daily_rank_pipeline_runner,
)
from app.services.globalapi_sync import (
    run_globalapi_sync_runner_in_app,
    stop_globalapi_sync_runner,
)
from app.services.jump_replay_cleanup import (
    run_jump_replay_cleanup_runner_in_app,
    stop_jump_replay_cleanup_runner,
)
from app.services.live_streams import (
    run_live_stream_runner_in_app,
    stop_live_stream_runner,
)
from app.services.map_file_distribution_worker import (
    run_map_file_distribution_runner,
    stop_map_file_distribution_runner,
)
from app.services.player_session_timeout import (
    run_player_session_timeout_runner_in_app,
    stop_player_session_timeout_runner,
)
from app.services.player_steam_profile_events import (
    listen_for_player_steam_profile_updates,
)
from app.services.player_steam_profile_events import (
    stop_listener as stop_player_steam_profile_listener,
)
from app.services.record_events import (
    listen_for_recent_record_updates,
)
from app.services.record_events import (
    stop_listener as stop_record_listener,
)
from app.services.server_collector import (
    run_server_query_collector_in_app,
    stop_collector,
)
from app.services.server_events import listen_for_server_updates, stop_listener
from app.services.youtube_media import (
    run_media_sync_runner_in_app,
    stop_media_sync_runner,
)

configure_app_logging(settings.LOG_LEVEL)


def custom_generate_unique_id(route: APIRoute) -> str:
    if route.tags:
        return f"{route.tags[0]}-{route.name}"
    return route.name


if settings.SENTRY_DSN and settings.ENVIRONMENT != "local":
    sentry_sdk.init(dsn=str(settings.SENTRY_DSN), enable_tracing=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    listener_task = asyncio.create_task(listen_for_server_updates())
    recent_record_listener_task = asyncio.create_task(
        listen_for_recent_record_updates()
    )
    player_steam_profile_listener_task = asyncio.create_task(
        listen_for_player_steam_profile_updates()
    )
    collector_task: asyncio.Task[None] | None = None
    globalapi_sync_task: asyncio.Task[None] | None = None
    daily_rank_pipeline_task: asyncio.Task[None] | None = None
    player_session_timeout_task: asyncio.Task[None] | None = None
    live_stream_task: asyncio.Task[None] | None = None
    media_sync_task: asyncio.Task[None] | None = None
    jump_replay_cleanup_task: asyncio.Task[None] | None = None
    map_file_distribution_task: asyncio.Task[None] | None = None
    if settings.RUN_SERVER_STATUS_COLLECTOR_IN_APP:
        collector_task = asyncio.create_task(run_server_query_collector_in_app())
    if settings.RUN_GLOBALAPI_SYNC_RUNNER_IN_APP:
        globalapi_sync_task = asyncio.create_task(run_globalapi_sync_runner_in_app())
    if settings.RUN_DAILY_RANK_PIPELINE_TASK_RUNNER_IN_APP:
        daily_rank_pipeline_task = asyncio.create_task(
            run_daily_rank_pipeline_runner_in_app()
        )
    if settings.RUN_PLAYER_SESSION_TIMEOUT_RUNNER_IN_APP:
        player_session_timeout_task = asyncio.create_task(
            run_player_session_timeout_runner_in_app()
        )
    if settings.RUN_LIVE_STREAM_RUNNER_IN_APP:
        live_stream_task = asyncio.create_task(run_live_stream_runner_in_app())
    if settings.RUN_MEDIA_SYNC_RUNNER_IN_APP:
        media_sync_task = asyncio.create_task(run_media_sync_runner_in_app())
    if settings.RUN_JUMP_REPLAY_CLEANUP_RUNNER_IN_APP:
        jump_replay_cleanup_task = asyncio.create_task(
            run_jump_replay_cleanup_runner_in_app()
        )
    if settings.RUN_MAP_FILE_DISTRIBUTION_RUNNER_IN_APP:
        map_file_distribution_task = asyncio.create_task(
            run_map_file_distribution_runner()
        )
    try:
        yield
    finally:
        await stop_listener(listener_task)
        await stop_record_listener(recent_record_listener_task)
        await stop_player_steam_profile_listener(player_steam_profile_listener_task)
        await stop_collector(collector_task)
        await stop_globalapi_sync_runner(globalapi_sync_task)
        await stop_daily_rank_pipeline_runner(daily_rank_pipeline_task)
        await stop_player_session_timeout_runner(player_session_timeout_task)
        await stop_live_stream_runner(live_stream_task)
        await stop_media_sync_runner(media_sync_task)
        await stop_jump_replay_cleanup_runner(jump_replay_cleanup_task)
        await stop_map_file_distribution_runner(map_file_distribution_task)


app = FastAPI(
    title=settings.PROJECT_NAME,
    docs_url=None,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan,
)

# Set all CORS enabled origins
if settings.all_cors_origins or settings.cors_allow_origin_regex:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.all_cors_origins,
        allow_origin_regex=settings.cors_allow_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(misc_router, prefix="/api/v1", include_in_schema=False)
app.include_router(v0_router)

_openapi_v0_schema: dict[str, Any] | None = None
_openapi_v1_schema: dict[str, Any] | None = None


def _format_openapi_tag(tag: str) -> str:
    return tag.replace("-", " ").replace("_", " ").title()


def _format_openapi_tags(schema: dict[str, Any]) -> dict[str, Any]:
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            tags = operation.get("tags")
            if isinstance(tags, list):
                operation["tags"] = [
                    _format_openapi_tag(tag) if isinstance(tag, str) else tag
                    for tag in tags
                ]
    return schema


def _build_openapi_schema(
    prefix: str,
    title: str,
    version: str,
    description: str,
) -> dict[str, Any]:
    routes = [
        route
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path.startswith(prefix)
        and route.include_in_schema
    ]
    schema = get_openapi(
        title=title,
        version=version,
        description=description,
        routes=routes,
    )
    return _format_openapi_tags(schema)


def custom_openapi_v1() -> dict[str, Any]:
    global _openapi_v1_schema
    if _openapi_v1_schema is None:
        _openapi_v1_schema = _build_openapi_schema(
            settings.API_V1_STR,
            f"{settings.PROJECT_NAME} v1",
            "v1",
            "v1 for project endpoints.",
        )
    return _openapi_v1_schema


app.openapi = custom_openapi_v1


@app.get("/v0/openapi.json", include_in_schema=False)
def openapi_v0() -> dict[str, Any]:
    global _openapi_v0_schema
    if _openapi_v0_schema is None:
        _openapi_v0_schema = _build_openapi_schema(
            "/v0",
            f"{settings.PROJECT_NAME} v0",
            "v0",
            "v0 for GlobalAPI v2.0 compatibility.",
        )
    return _openapi_v0_schema


@app.get("/docs", include_in_schema=False)
def swagger_ui() -> HTMLResponse:
    swagger_ui_parameters = swagger_ui_default_parameters.copy()
    swagger_ui_parameters.update(
        {
            "url": f"{settings.API_V1_STR}/openapi.json",
            "urls": [
                {
                    "url": f"{settings.API_V1_STR}/openapi.json",
                    "name": "v1",
                },
                {
                    "url": "/v0/openapi.json",
                    "name": "v0 (GlobalAPI v2.0 compat)",
                },
            ],
            "urls.primaryName": "v1",
            "docExpansion": "none",
            "layout": "StandaloneLayout",
        }
    )

    swagger_js_url = (
        "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"
    )
    swagger_standalone_url = (
        "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-standalone-preset.js"
    )
    swagger_css_url = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css"
    swagger_favicon_url = "https://fastapi.tiangolo.com/img/favicon.png"
    title = f"{settings.PROJECT_NAME} - API Docs"

    params = ""
    for key, value in swagger_ui_parameters.items():
        params += f"{json.dumps(key)}: {json.dumps(jsonable_encoder(value))},\n"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link type="text/css" rel="stylesheet" href="{swagger_css_url}">
    <link rel="shortcut icon" href="{swagger_favicon_url}">
    <title>{title}</title>
    </head>
    <body>
    <div id="swagger-ui">
    </div>
    <script src="{swagger_js_url}"></script>
    <script src="{swagger_standalone_url}"></script>
    <!-- `SwaggerUIBundle` is now available on the page -->
    <script>
    const ui = SwaggerUIBundle({{
        {params}
    presets: [
        SwaggerUIBundle.presets.apis,
        SwaggerUIStandalonePreset
        ],
    }})
    </script>
    </body>
    </html>
    """
    return HTMLResponse(html)
