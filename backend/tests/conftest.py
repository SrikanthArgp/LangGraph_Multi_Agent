import asyncio
import os
import sys
from collections.abc import AsyncGenerator

import fakeredis
import pytest
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession

load_dotenv()

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
