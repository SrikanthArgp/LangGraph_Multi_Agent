import asyncio
import os
import sys
import uuid
from collections.abc import AsyncGenerator

import fakeredis
import pytest
from dotenv import load_dotenv
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

load_dotenv()  # must run before api.dependencies/api.main import db.base, which reads os.environ

from api.dependencies import get_db, get_graph, get_redis
from api.main import create_app
from auth.dependencies import get_db_session, get_redis_client

if sys.platform == "win32":
    # psycopg's async mode cannot run on the default ProactorEventLoop on Windows.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _skip_if_missing(var_name: str) -> None:
    if not os.environ.get(var_name):
        pytest.skip(f"{var_name} not set in .env — skipping check that needs it")


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Real Postgres session wrapped in a rolled-back SAVEPOINT, so tests can write real
    rows to the shared dev DB without leaving anything behind. `session.commit()` inside
    a test/request only releases the SAVEPOINT (still inside the outer transaction this
    fixture opened), so nothing here is durable past the test regardless of what the
    code under test does.
    """
    _skip_if_missing("DATABASE_URL")
    from db.base import engine

    async with engine.connect() as conn:
        await conn.begin()
        session = AsyncSession(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        try:
            yield session
        finally:
            await session.close()
            await conn.rollback()


@pytest.fixture
async def fake_redis() -> AsyncGenerator[fakeredis.aioredis.FakeRedis, None]:
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture(scope="session")
def pg_conn():
    _skip_if_missing("DATABASE_URL_PSYCOPG")
    import psycopg

    conn = psycopg.connect(os.environ["DATABASE_URL_PSYCOPG"])
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def pg_sync_engine():
    _skip_if_missing("DATABASE_URL")
    from sqlalchemy import create_engine

    engine = create_engine(os.environ["DATABASE_URL"])
    yield engine
    engine.dispose()


@pytest.fixture
async def redis_async_client():
    _skip_if_missing("REDIS_URL")
    import redis.asyncio as aioredis

    client = aioredis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    yield client
    await client.aclose()


class FakeGraph:
    """Stands in for the compiled CRAG graph in tests that don't need a real LLM call -
    ownership/validation/error-path tests care about everything except what the graph
    actually returns.
    """

    def __init__(self, generation: str = "fake answer", web_search: bool = False):
        self.generation = generation
        self.web_search = web_search
        self.calls: list[dict] = []

    async def ainvoke(self, inputs: dict, config: dict) -> dict:
        self.calls.append({"inputs": inputs, "config": config})
        return {"generation": self.generation, "web_search": self.web_search, "documents": []}


class FailingGraph:
    async def ainvoke(self, inputs: dict, config: dict) -> dict:
        raise RuntimeError("simulated graph failure")


@pytest.fixture
def fake_graph() -> FakeGraph:
    return FakeGraph()


@pytest.fixture
async def app(db_session: AsyncSession, fake_redis: fakeredis.aioredis.FakeRedis, fake_graph: FakeGraph):
    application = create_app()

    async def _get_db():
        yield db_session

    async def _get_redis():
        return fake_redis

    async def _get_graph():
        yield fake_graph

    application.dependency_overrides[get_db] = _get_db
    application.dependency_overrides[get_redis] = _get_redis
    application.dependency_overrides[get_graph] = _get_graph
    # Same overrides api/main.py's lifespan wires for the real app - get_current_user must
    # resolve to the same test session/redis, not its own ad-hoc providers.
    application.dependency_overrides[get_db_session] = _get_db
    application.dependency_overrides[get_redis_client] = _get_redis

    yield application

    application.dependency_overrides.clear()


@pytest.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    # raise_app_exceptions=False: Starlette's ServerErrorMiddleware sends the fallback 500
    # response via `send()` and then re-raises the original exception regardless (so a real
    # ASGI server can still log it) - httpx's default (True) treats that re-raise as "the app
    # raised" and surfaces it to the test instead of the Response it already built. We want to
    # assert on the response an actual client receives (a clean 500 JSON body), not get a raw
    # traceback in the test itself - that's exactly what api/error_handlers.py's generic
    # handler exists to prevent.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def registered_user(client: AsyncClient) -> dict:
    """Registers a fresh user and returns {"email", "password", "headers", "user", "tokens"}."""
    email = f"test_{uuid.uuid4().hex[:12]}@example.com"
    password = "test12345"
    response = await client.post(
        "/v1/auth/register",
        json={"email": email, "username": f"user_{uuid.uuid4().hex[:8]}", "password": password},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return {
        "email": email,
        "password": password,
        "headers": {"Authorization": f"Bearer {body['tokens']['access_token']}"},
        "user": body["user"],
        "tokens": body["tokens"],
    }
