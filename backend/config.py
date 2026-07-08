import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Every secret currently read from backend/.env, whether via this file's Settings or via the
# os.getenv-reading Phase 1-4 modules below. In production these come from SSM instead - see
# bootstrap_env().
_SSM_SECRET_KEYS = [
    "DATABASE_URL",
    "DATABASE_URL_PSYCOPG",
    "REDIS_URL",
    "JWT_SECRET_KEY",
    "OPENAI_API_KEY",
    "TAVILY_API_KEY",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "GRAFANA_OTLP_TOKEN",
]


def bootstrap_env() -> None:
    """Populate os.environ with every secret before anything that reads them gets imported.

    This has to run first, and it has to populate real process environment variables, not
    just this module's Settings fields - db/base.py's `create_async_engine(os.environ[...])`
    and auth/jwt.py's/auth/dependencies.py's os.environ reads run at their own *import* time,
    not lazily through Settings (a deliberate Phase 6 decision not to retrofit them, see
    completed.md). The OpenAI/Tavily SDKs used by multi_agent/chains/* read their API keys
    the same import-time way. Settings() below still works unchanged in both branches, since
    pydantic-settings prefers a real env var over its own env_file read - populating
    os.environ here already wins by the time get_settings() constructs it.

    Two sources, chosen by APP_ENV (itself a plain, non-secret env var - set directly on the
    Lambda function's config in production, defaulted to "development" in .env locally):
    production fetches every key in _SSM_SECRET_KEYS from SSM Parameter Store; anything else
    loads backend/.env via python-dotenv, unchanged from pre-Phase-15 behavior.
    """
    if os.environ.get("APP_ENV") == "production":
        _bootstrap_from_ssm()
    else:
        load_dotenv()


def _bootstrap_from_ssm() -> None:
    # Deferred import: boto3 only lives in the `prod` extra, and only production actually
    # needs it - importing it unconditionally at module load would make config.py (imported
    # by nearly everything) require boto3 even for local/dev/test runs that never call this.
    import boto3

    prefix = os.environ.get("SSM_PARAMETER_PREFIX", "/crag/prod")
    client = boto3.client("ssm")
    for key in _SSM_SECRET_KEYS:
        response = client.get_parameter(Name=f"{prefix}/{key}", WithDecryption=True)
        os.environ[key] = response["Parameter"]["Value"]


class Settings(BaseSettings):
    """Centralized settings for all Phase 6+ code (api/, and anything those routers touch).

    Phase 1-4 modules (db/base.py, auth/*, cache/*) keep reading os.getenv directly -
    intentionally not retrofitted, see completed.md's Phase 6 config.py decision. A missing
    or malformed required var here fails at Settings() construction (app startup), not deep
    inside a request. Call bootstrap_env() before constructing this (api/main.py does, at
    import time) so both this class and those Phase 1-4 modules see the same values
    regardless of source.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # PostgreSQL
    database_url: str
    database_url_psycopg: str
    database_pool_min_size: int = 2
    database_pool_max_size: int = 10

    # Redis
    redis_url: str

    # JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # App
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    cors_origins: str = "http://localhost:3000"

    # Auth rate limiting (separate, stricter, IP-keyed bucket from Phase 12's general per-user limiter)
    rate_limit_auth_per_minute: int = 10

    # General per-user rate limiting (Phase 12), applied to authenticated sessions/chat routes
    rate_limit_general_per_minute: int = 60

    # OpenTelemetry / Grafana Cloud (Phase 14) — all optional. api/otel_client.py degrades to
    # local-only spans (never exported) when any of these are missing, same fail-open pattern
    # as observability/langfuse_client.get_langfuse_handler().
    otel_exporter_otlp_endpoint: str | None = None
    grafana_otlp_instance_id: str | None = None
    grafana_otlp_token: str | None = None

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from .env / environment
