import secrets
import warnings
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AnyUrl,
    BeforeValidator,
    HttpUrl,
    PostgresDsn,
    computed_field,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


def parse_cors(v: Any) -> list[str] | str:
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",") if i.strip()]
    elif isinstance(v, list | str):
        return v
    raise ValueError(v)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Use top level .env file (one level above ./backend/)
        env_file="../.env",
        env_ignore_empty=True,
        extra="ignore",
    )
    API_V1_STR: str = "/v1"
    SECRET_KEY: str = secrets.token_urlsafe(32)
    # 60 minutes * 24 hours * 8 days = 8 days
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8
    FRONTEND_HOST: str = "http://localhost:5173"
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"
    ENABLE_TEST_AUTH_HELPERS: bool = False

    BACKEND_CORS_ORIGINS: Annotated[
        list[AnyUrl] | str, BeforeValidator(parse_cors)
    ] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_cors_origins(self) -> list[str]:
        return [str(origin).rstrip("/") for origin in self.BACKEND_CORS_ORIGINS] + [
            self.FRONTEND_HOST
        ]

    PROJECT_NAME: str
    SENTRY_DSN: HttpUrl | None = None
    POSTGRES_SERVER: str
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> PostgresDsn:
        return PostgresDsn.build(
            scheme="postgresql+psycopg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        )

    STEAM_API_KEY: str | None = None
    STEAM_SERVER_LIST_APP_ID: int = 4465480
    STEAM_SERVER_LIST_LIMIT: int = 50_000
    GLOBALAPI_BASE_URL: str = "https://kztimerglobal.com/api/v2.0"
    GLOBALAPI_TIMEOUT_SECONDS: float = 45.0
    GLOBALAPI_HTTPX_TRUST_ENV: bool = False
    GLOBALAPI_SYNC_RUNNER_POLL_SECONDS: int = 1
    GLOBALAPI_SYNC_FAILURE_RETRY_SECONDS: int = 60
    TASK_RUNNER_POLL_SECONDS: int = 1
    GLOBALAPI_SYNC_STALE_AFTER_SECONDS: int = 86_400
    GLOBALAPI_SERVERS_SYNC_STALE_AFTER_SECONDS: int = 86_400
    GLOBALAPI_BANS_SYNC_STALE_AFTER_SECONDS: int = 60
    GLOBALAPI_RECORD_FILTERS_SYNC_STALE_AFTER_SECONDS: int = 86_400
    GLOBALAPI_RECORD_FILTERS_SYNC_HOUR_UTC: int = 2
    DAILY_RANK_PIPELINE_TASK_HOUR_UTC: int = 0
    GLOBALAPI_RECORDS_SYNC_STALE_AFTER_SECONDS: int = 0
    GLOBALAPI_SERVERS_LIMIT: int = 9_999
    GLOBALAPI_BANS_BACKFILL_LIMIT: int = 1_000
    GLOBALAPI_BANS_INCREMENTAL_LIMIT: int = 10
    GLOBALAPI_BANS_INCREMENTAL_OVERLAP_SECONDS: int = 5
    GLOBALAPI_RECORD_FILTERS_LIMIT: int = 1_000
    RUN_SERVER_STATUS_COLLECTOR_IN_APP: bool = True
    RUN_GLOBALAPI_SYNC_RUNNER_IN_APP: bool = True
    RUN_DAILY_RANK_PIPELINE_TASK_RUNNER_IN_APP: bool = True
    LOG_LEVEL: str = "INFO"
    GEOIP_CITY_DB_PATH: Path = Path("../.geoip/GeoLite2-City.mmdb")
    SUPER_USER_STEAMID64: int

    def _check_default_secret(self, var_name: str, value: str | None) -> None:
        if value == "changethis":
            message = (
                f'The value of {var_name} is "changethis", '
                "for security, please change it, at least for deployments."
            )
            if self.ENVIRONMENT == "local":
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)

    @model_validator(mode="after")
    def _enforce_non_default_secrets(self) -> Self:
        self._check_default_secret("SECRET_KEY", self.SECRET_KEY)
        self._check_default_secret("POSTGRES_PASSWORD", self.POSTGRES_PASSWORD)
        return self


settings = Settings()  # type: ignore
