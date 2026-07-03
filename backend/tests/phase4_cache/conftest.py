import pytest
from fakeredis import aioredis as fakeredis_aioredis


@pytest.fixture
async def fake_redis():
    client = fakeredis_aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()
