import asyncio
import os
import sys

import pytest
from dotenv import load_dotenv

load_dotenv()

if sys.platform == "win32":
    # psycopg's async mode cannot run on the default ProactorEventLoop on Windows.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _skip_if_missing(var_name: str) -> None:
    if not os.environ.get(var_name):
        pytest.skip(f"{var_name} not set in .env — skipping check that needs it")


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
