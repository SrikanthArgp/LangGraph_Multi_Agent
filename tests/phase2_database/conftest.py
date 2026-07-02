import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import engine


@pytest.fixture
async def db_session():
    async with engine.connect() as conn:
        await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            await session.close()
            await conn.rollback()
