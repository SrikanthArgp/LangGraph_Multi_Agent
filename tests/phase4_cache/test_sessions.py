import uuid
from datetime import datetime, timedelta, timezone

from cache.sessions import (
    add_session_to_listing,
    get_recent_messages,
    get_recent_sessions,
    get_session_meta,
    is_token_revoked,
    push_message,
    revoke_token,
    set_session_meta,
)


def _now_plus(seconds: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


async def test_add_session_to_listing_keeps_only_5_most_recent(fake_redis):
    user_id = uuid.uuid4()
    session_ids = [uuid.uuid4() for _ in range(6)]

    for i, session_id in enumerate(session_ids):
        await add_session_to_listing(fake_redis, user_id, session_id, _now_plus(i))

    recent = await get_recent_sessions(fake_redis, user_id)
    assert len(recent) == 5
    assert str(session_ids[0]) not in recent
    assert recent[0] == str(session_ids[-1])


async def test_get_recent_sessions_refreshes_ttl(fake_redis):
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    await add_session_to_listing(fake_redis, user_id, session_id, datetime.now(timezone.utc))

    await get_recent_sessions(fake_redis, user_id)

    ttl = await fake_redis.ttl(f"user:{user_id}:sessions")
    assert ttl > 0


async def test_session_meta_round_trip(fake_redis):
    session_id = uuid.uuid4()
    await set_session_meta(fake_redis, session_id, title="My session", is_archived="0")

    meta = await get_session_meta(fake_redis, session_id)

    assert meta["title"] == "My session"
    assert meta["is_archived"] == "0"


async def test_session_meta_has_ttl_after_write(fake_redis):
    session_id = uuid.uuid4()
    await set_session_meta(fake_redis, session_id, title="x")

    ttl = await fake_redis.ttl(f"session:{session_id}:meta")
    assert ttl > 0


async def test_push_message_trims_to_20_most_recent(fake_redis):
    session_id = uuid.uuid4()
    for i in range(25):
        await push_message(fake_redis, session_id, {"id": str(i), "role": "user", "content": f"msg {i}"})

    messages = await get_recent_messages(fake_redis, session_id)

    assert len(messages) == 20
    assert messages[0]["id"] == "5"
    assert messages[-1]["id"] == "24"


async def test_get_recent_messages_round_trips_json(fake_redis):
    session_id = uuid.uuid4()
    await push_message(fake_redis, session_id, {"id": "1", "role": "assistant", "content": "hello"})

    messages = await get_recent_messages(fake_redis, session_id)

    assert messages == [{"id": "1", "role": "assistant", "content": "hello"}]


async def test_revoke_token_then_is_token_revoked_true(fake_redis):
    jti = str(uuid.uuid4())
    assert not await is_token_revoked(fake_redis, jti)

    await revoke_token(fake_redis, jti, ttl_seconds=900)

    assert await is_token_revoked(fake_redis, jti)
    ttl = await fake_redis.ttl(f"revoked_token:{jti}")
    assert 0 < ttl <= 900


async def test_revoke_token_with_non_positive_ttl_is_a_no_op(fake_redis):
    jti = str(uuid.uuid4())

    await revoke_token(fake_redis, jti, ttl_seconds=0)

    assert not await is_token_revoked(fake_redis, jti)
