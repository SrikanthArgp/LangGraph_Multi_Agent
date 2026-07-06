import pytest
from httpx import AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import api.dependencies as deps
from api.dependencies import get_db, get_redis

pytestmark = pytest.mark.requires_db


class _AlwaysFailsPing:
    async def ping(self):
        raise RedisConnectionError("simulated Redis outage")


async def test_health_ok_when_db_and_redis_up(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": True, "redis": True}


async def test_health_degrades_not_fails_when_redis_down(client: AsyncClient, app):
    """Redis is fail-open everywhere else in this app (Phase 3/4/6) - /health should reflect
    that: a Redis outage is "degraded", not the 503/500 a hard-dependency outage would be.
    """
    app.dependency_overrides[get_redis] = lambda: _AlwaysFailsPing()

    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "degraded", "db": True, "redis": False}


async def test_health_returns_503_when_db_down(client: AsyncClient, app, monkeypatch):
    """Postgres is a hard dependency - unlike Redis, its outage should make /health report
    unavailable via the same 503 path every other route gets from get_db's own
    OperationalError handling (api/dependencies.py), not a 200 with a degraded flag.
    """
    broken_engine = create_async_engine(
        "postgresql+psycopg://baduser:badpass@127.0.0.1:1/nonexistent",
        pool_pre_ping=False,
        connect_args={"connect_timeout": 2},
    )
    broken_factory = async_sessionmaker(broken_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(deps, "async_session_factory", broken_factory)
    app.dependency_overrides.pop(get_db, None)  # use the real get_db, not the fixture's fake session

    try:
        response = await client.get("/health")
        assert response.status_code == 503
        assert response.json() == {"detail": "Database unavailable"}
    finally:
        await broken_engine.dispose()
