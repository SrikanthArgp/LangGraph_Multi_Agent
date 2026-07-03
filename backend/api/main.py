import asyncio
import logging
import sys
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

if sys.platform == "win32":
    # psycopg's async mode cannot run on the default ProactorEventLoop - same fix as
    # db/migrations/env.py and tests/conftest.py. This covers import paths that respect the
    # event loop policy (e.g. pytest-asyncio, `python -c "from api.main import app"`). It does
    # NOT cover `uvicorn api.main:app` / uvicorn.run() - modern uvicorn passes its own
    # loop_factory straight to asyncio.run(), bypassing the policy entirely, and hardcodes
    # ProactorEventLoop on win32 for the "asyncio"/"auto" loop. Run via run_api.py instead,
    # which supplies a SelectorEventLoop factory uvicorn will actually use.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from api.dependencies import get_db, get_redis
from api.error_handlers import register_error_handlers
from api.routers import auth, chat, sessions
from auth.dependencies import get_db_session, get_redis_client
from config import get_settings
from db.base import engine as db_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # Fail-fast, not suppressed: if Postgres/Redis is unreachable here, uvicorn should
    # refuse to boot with a clear error rather than start in a half-working state - see
    # Resilience & Crash Prevention in plan.md.
    app.state.pg_pool = AsyncConnectionPool(
        conninfo=settings.database_url_psycopg,
        min_size=settings.database_pool_min_size,
        max_size=settings.database_pool_max_size,
        open=False,
        # autocommit=True is required by AsyncPostgresSaver.setup() - its migrations include
        # CREATE INDEX CONCURRENTLY, which Postgres refuses to run inside a transaction block
        # (confirmed by actually hitting `psycopg.errors.ActiveSqlTransaction` without this).
        kwargs={"autocommit": True},
    )
    await app.state.pg_pool.open()
    # AsyncPostgresSaver isn't an async context manager in langgraph-checkpoint-postgres>=2.0
    # (verified against the installed version - plan.md's original `async with AsyncPostgresSaver(...)
    # as saver:` snippet raises TypeError; that pattern belongs to from_conn_string()'s
    # @asynccontextmanager factory, not a direct constructor call).
    saver = AsyncPostgresSaver(app.state.pg_pool)
    await saver.setup()  # creates checkpoint tables if they don't already exist (idempotent)

    # Reuse db/base.py's engine rather than opening a second pool against the same database -
    # plan.md's lifespan snippet creates its own `create_async_engine(...)` here, but that
    # engine would sit unused (all queries already go through db/base.py's async_session_factory
    # via api/dependencies.get_db) while doubling Supabase pooler connection usage for nothing.
    # This reference exists for Phase 13's SQLAlchemyInstrumentor, which needs to instrument
    # the engine that's actually queried.
    app.state.db_engine = db_engine

    app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)

    yield

    await app.state.pg_pool.close()
    await app.state.redis.aclose()


def create_app() -> FastAPI:
    app = FastAPI(title="CRAG Multi-Agent API", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    register_error_handlers(app)

    # auth/dependencies.py's get_current_user was built (Phase 3) with its own default
    # get_db_session/get_redis_client providers specifically so it could stay self-contained
    # until this override existed - see completed.md's Phase 3 note. Without this, every
    # authenticated request opened a second, ad-hoc DB session and Redis connection alongside
    # the request-scoped ones api/dependencies.get_db/get_redis already provide.
    app.dependency_overrides[get_db_session] = get_db
    app.dependency_overrides[get_redis_client] = get_redis

    app.include_router(auth.router, prefix="/v1")
    app.include_router(sessions.router, prefix="/v1")
    app.include_router(chat.router, prefix="/v1")

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
