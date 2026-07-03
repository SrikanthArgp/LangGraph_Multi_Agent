from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized settings for all Phase 6+ code (api/, and anything those routers touch).

    Phase 1-4 modules (db/base.py, auth/*, cache/*) keep reading os.getenv directly -
    intentionally not retrofitted, see completed.md's Phase 6 config.py decision. A missing
    or malformed required var here fails at Settings() construction (app startup), not deep
    inside a request.
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

    # Auth rate limiting (separate, stricter bucket from Phase 11's general per-user limiter)
    rate_limit_auth_per_minute: int = 10

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from .env / environment
