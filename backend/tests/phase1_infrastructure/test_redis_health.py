import pytest

pytestmark = pytest.mark.requires_redis


def test_ping(redis_client):
    assert redis_client.ping() is True


def test_eviction_policy_is_allkeys_lru(redis_client):
    policy = redis_client.config_get("maxmemory-policy")
    assert policy.get("maxmemory-policy") == "allkeys-lru"


def test_zset_session_listing_pattern_roundtrip(redis_client):
    key = "healthcheck:user:test-user:sessions"
    redis_client.delete(key)
    redis_client.zadd(key, {"session-a": 1, "session-b": 2})
    redis_client.expire(key, 30)
    assert redis_client.zrevrange(key, 0, -1) == ["session-b", "session-a"]
    assert redis_client.ttl(key) > 0
    redis_client.delete(key)


def test_hash_session_meta_pattern_roundtrip(redis_client):
    key = "healthcheck:session:test-session:meta"
    redis_client.delete(key)
    redis_client.hset(key, mapping={"title": "healthcheck", "is_archived": "0"})
    redis_client.expire(key, 30)
    assert redis_client.hget(key, "title") == "healthcheck"
    redis_client.delete(key)


def test_list_messages_pattern_roundtrip(redis_client):
    key = "healthcheck:session:test-session:messages"
    redis_client.delete(key)
    redis_client.rpush(key, "msg-1", "msg-2")
    redis_client.ltrim(key, -20, -1)
    assert redis_client.lrange(key, 0, -1) == ["msg-1", "msg-2"]
    redis_client.delete(key)


def test_string_revocation_pattern_with_ttl(redis_client):
    key = "healthcheck:revoked_token:test-jti"
    redis_client.delete(key)
    redis_client.set(key, "1", ex=5, nx=True)
    assert redis_client.exists(key) == 1
    assert 0 < redis_client.ttl(key) <= 5
    redis_client.delete(key)
