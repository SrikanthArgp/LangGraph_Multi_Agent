import os

import pytest

from tests.conftest import _skip_if_missing


@pytest.fixture(scope="session")
def redis_client():
    _skip_if_missing("REDIS_URL")
    import redis

    client = redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    yield client
    client.close()


@pytest.fixture(scope="session")
def chroma_retriever():
    from multi_agent.ingestion import retriever

    return retriever
