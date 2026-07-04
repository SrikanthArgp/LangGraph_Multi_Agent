import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


_pool_min = int(os.environ.get("DATABASE_POOL_MIN_SIZE", 2))
_pool_max = int(os.environ.get("DATABASE_POOL_MAX_SIZE", 10))

engine = create_async_engine(
    os.environ["DATABASE_URL"],
    pool_size=_pool_min,
    max_overflow=_pool_max - _pool_min,
    pool_pre_ping=True,
    # DATABASE_URL is Supabase's Transaction pooler (pgbouncer, port 6543): it can hand a
    # different backend Postgres process to the same client connection between transactions.
    # psycopg3 auto-prepares statements after repeated use (prepare_threshold=5 by default)
    # and caches them per client connection - under pgbouncer transaction mode, a statement
    # prepared against one backend can get executed against a different one after a swap,
    # producing intermittent failures (reproduced as `db.refresh()` raising "Could not
    # refresh instance" right after a successful `flush()`, i.e. the immediate follow-up
    # SELECT silently missing the just-inserted row). Disabling statement preparation
    # entirely is psycopg/Supabase's own documented fix for this exact combination.
    connect_args={"prepare_threshold": None},
)

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
