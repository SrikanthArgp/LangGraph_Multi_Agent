import uuid
from datetime import datetime, timezone

import pytest

from cache.sessions import (
    _meta_key,
    _messages_key,
    _revoked_token_key,
    _sessions_key,
    add_session_to_listing,
    get_recent_messages,
    get_recent_sessions,
    get_session_meta,
    is_token_revoked,
    push_message,
    revoke_token,
    set_session_meta,
)

pytestmark = pytest.mark.requires_redis


async def test_add_and_get_recent_sessions_against_real_redis(redis_async_client):
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    try:
        await add_session_to_listing(redis_async_client, user_id, session_id, datetime.now(timezone.utc))
        recent = await get_recent_sessions(redis_async_client, user_id)
        assert recent == [str(session_id)]
    finally:
        await redis_async_client.delete(_sessions_key(user_id))


async def test_session_meta_round_trip_against_real_redis(redis_async_client):
    session_id = uuid.uuid4()
    try:
        await set_session_meta(redis_async_client, session_id, title="real redis test")
        meta = await get_session_meta(redis_async_client, session_id)
        assert meta["title"] == "real redis test"
    finally:
        await redis_async_client.delete(_meta_key(session_id))


async def test_push_and_get_messages_against_real_redis(redis_async_client):
    session_id = uuid.uuid4()
    try:
        await push_message(redis_async_client, session_id, {"id": "1", "role": "user", "content": "hi"})
        messages = await get_recent_messages(redis_async_client, session_id)
        assert messages == [{"id": "1", "role": "user", "content": "hi"}]
    finally:
        await redis_async_client.delete(_messages_key(session_id))


async def test_revoke_and_check_token_against_real_redis(redis_async_client):
    jti = str(uuid.uuid4())
    try:
        assert not await is_token_revoked(redis_async_client, jti)
        await revoke_token(redis_async_client, jti, ttl_seconds=60)
        assert await is_token_revoked(redis_async_client, jti)
    finally:
        await redis_async_client.delete(_revoked_token_key(jti))
