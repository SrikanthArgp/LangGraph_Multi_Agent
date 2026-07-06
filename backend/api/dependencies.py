import logging
from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, Request, status
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from redis.exceptions import RedisError
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from config import  get_settings
from db.base import async_session_factory
from db.models import User
from multi_agent.graph import create_app

logger = logging.getLogger(__name__)

__all__ = [
    "get_db",
    "get_redis",
    "get_graph",
    "get_current_user",
    "enforce_auth_rate_limit",
    "enforce_general_rate_limit",
]


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Request-scoped DB session. Commits on a clean exit; a connection-level failure
    (OperationalError) is translated into a 503 instead of surfacing as an opaque 500 - see
    Resilience & Crash Prevention in plan.md. Other SQLAlchemy errors (e.g. IntegrityError
    from a duplicate email) are left to propagate - routers that can produce one catch it
    explicitly (see api/routers/auth.py's register endpoint) rather than have this dependency
    guess at the right status code for every possible business-logic failure.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except OperationalError as e:
            await session.rollback()
            logger.warning("db_unavailable", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable"
            ) from e
        except Exception:
            await session.rollback()
            raise


async def get_redis(request: Request) -> aioredis.Redis:
    """Raw Redis client singleton (created in api/main.py's lifespan). Deliberately does not
    catch connection errors here: every caller either has an explicit DB fallback
    (api/routers/sessions.py and chat.py catch cache.exceptions.CacheUnavailableError) or
    fails open by design (the auth rate limiter and the Phase 3 revocation check) - see
    "Fallback on Redis unavailability" in plan.md. A blanket 503 at this dependency would
    defeat both of those graceful-degrade paths.
    """
    return request.app.state.redis


async def get_graph(request: Request):
    """Compile the CRAG graph with a per-request AsyncPostgresSaver bound to the shared
    connection pool - cheap, since the pool (not the saver) is the actual singleton resource.

    AsyncPostgresSaver isn't an async context manager when constructed directly (verified
    against the installed langgraph-checkpoint-postgres - see api/main.py's lifespan for the
    same note), so this is a plain construction, not `async with`.
    """
    saver = AsyncPostgresSaver(request.app.state.pg_pool)
    yield create_app(saver)


async def enforce_auth_rate_limit(
    request: Request, redis: aioredis.Redis = Depends(get_redis)
) -> None:
    """IP-keyed rate limit for /v1/auth/login and /v1/auth/register - these run before any
    identity exists, so they can't use a per-user bucket (that's enforce_general_rate_limit's
    job, for authenticated endpoints). Redis INCR-with-TTL bucket, window resets every 60s.

    Fails open on a Redis outage (logs a warning, lets the request through) rather than 503ing
    the whole auth flow over a transient cache blip - same reasoning as the Phase 3 revocation
    check's fail-open decision.
    """
    client_ip = request.client.host if request.client else "unknown"
    key = f"ratelimit:auth:{client_ip}"
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 60)
    except RedisError:
        logger.warning("auth_rate_limit_unavailable", extra={"client_ip": client_ip})
        return

    if count > get_settings().rate_limit_auth_per_minute:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests, try again later",
        )


async def enforce_general_rate_limit(
    current_user: User = Depends(get_current_user), redis: aioredis.Redis = Depends(get_redis)
) -> None:
    """User-keyed rate limit (Phase 12) for authenticated endpoints (sessions/chat routers) -
    unlike enforce_auth_rate_limit, identity already exists here via get_current_user, so this
    buckets per user rather than per IP (avoids one shared office/NAT IP tripping the limit for
    every user behind it). Same Redis INCR-with-TTL pattern, same 60s window, same fail-open
    behavior on a Redis outage as every other Redis-dependent check in this app.

    Depends(get_current_user) here and the route's own Depends(get_current_user) resolve to
    the same cached call within a request (FastAPI dependency caching, default use_cache=True)
    - this doesn't add a second DB lookup.
    """
    key = f"ratelimit:general:{current_user.id}"
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 60)
    except RedisError:
        logger.warning("general_rate_limit_unavailable", extra={"user_id": str(current_user.id)})
        return

    if count > get_settings().rate_limit_general_per_minute:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests, try again later",
        )
