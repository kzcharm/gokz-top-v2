import re

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.cors import CORSMiddleware

from app.core.config import Settings


def _build_settings(**overrides: object) -> Settings:
    data: dict[str, object] = {
        "PROJECT_NAME": "test",
        "POSTGRES_SERVER": "127.0.0.1",
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": "postgres",
        "POSTGRES_DB": "app_test",
        "SUPER_USER_STEAMID64": 76561197960265728,
        "BACKEND_CORS_ORIGINS": [],
        "REPLAY_VIEWER_HOST": None,
    }
    data.update(overrides)
    return Settings(
        **data,
    )


def test_all_cors_origins_adds_replay_viewer_for_non_local_deployments() -> None:
    settings = _build_settings(
        ENVIRONMENT="production",
        FRONTEND_HOST="https://gokz.top",
    )

    assert settings.all_cors_origins == [
        "https://gokz.top",
        "https://replays.gokz.top",
        "https://cs2kz.org",
    ]


def test_all_cors_origins_prefers_explicit_replay_viewer_host() -> None:
    settings = _build_settings(
        ENVIRONMENT="staging",
        FRONTEND_HOST="https://staging.gokz.top",
        REPLAY_VIEWER_HOST="https://replay-viewer-staging.kzcharm.com/",
        BACKEND_CORS_ORIGINS=[
            "https://api-console.kzcharm.com/",
            "https://staging.gokz.top",
        ],
    )

    assert settings.all_cors_origins == [
        "https://api-console.kzcharm.com",
        "https://staging.gokz.top",
        "https://replay-viewer-staging.kzcharm.com",
        "https://cs2kz.org",
    ]


def test_cors_wildcard_uses_regex_to_support_credentials() -> None:
    settings = _build_settings(
        ENVIRONMENT="production",
        FRONTEND_HOST="https://gokz.top",
        BACKEND_CORS_ORIGINS="*",
    )

    assert settings.all_cors_origins == []
    assert settings.cors_allow_origin_regex == ".*"


def test_wildcard_cors_reflects_origin_for_credentialed_requests() -> None:
    settings = _build_settings(
        ENVIRONMENT="production",
        FRONTEND_HOST="https://gokz.top",
        BACKEND_CORS_ORIGINS="*",
    )
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.all_cors_origins,
        allow_origin_regex=settings.cors_allow_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    def read_root() -> dict[str, bool]:
        return {"ok": True}

    response = TestClient(app).get("/", headers={"Origin": "https://gokz.top"})

    assert response.headers["access-control-allow-origin"] == "https://gokz.top"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_allow_origin_regex_allows_localhost_and_axekz_hosts() -> None:
    settings = _build_settings()

    assert settings.cors_allow_origin_regex is not None
    assert settings.cors_allow_origin_regex

    allowed_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:8000",
        "https://axekz.com",
        "https://www.axekz.com",
        "https://api.axekz.com",
    ]

    for origin in allowed_origins:
        assert re.fullmatch(settings.cors_allow_origin_regex, origin)
