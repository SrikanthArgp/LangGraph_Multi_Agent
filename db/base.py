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
)

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
