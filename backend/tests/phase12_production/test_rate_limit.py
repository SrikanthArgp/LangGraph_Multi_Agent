import pytest
from httpx import AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError

import api.dependencies as deps
from api.dependencies import get_redis

pytestmark = pytest.mark.requires_db


class _FakeSettings:
    rate_limit_general_per_minute = 2
    rate_limit_auth_per_minute = 10  # unrelated to this test, but auth routes also read it


class _AlwaysFailsRedis:
    """Every method (incr, zrevrange, hgetall, ...) raises - not just the one the rate
    limiter calls, since the route body under test also calls the cache layer directly
    (cache/sessions.py), and that needs to see the same simulated outage.
    """

    def __getattr__(self, _name):
        async def _raise(*_args, **_kwargs):
            raise RedisConnectionError("simulated Redis outage")

        return _raise


async def test_general_rate_limit_returns_429_after_exceeding_bucket(
    client: AsyncClient, registered_user: dict, monkeypatch
):
    monkeypatch.setattr(deps, "get_settings", lambda: _FakeSettings())
    headers = registered_user["headers"]

    for _ in range(2):
        response = await client.get("/v1/sessions", headers=headers)
        assert response.status_code == 200

    response = await client.get("/v1/sessions", headers=headers)
    assert response.status_code == 429
    assert response.json() == {"detail": "Too many requests, try again later"}


async def test_general_rate_limit_is_keyed_per_user_not_shared(
    client: AsyncClient, registered_user: dict, monkeypatch
):
    """A second user must not inherit the first user's exhausted bucket - this is the whole
    point of switching from the auth endpoints' IP-keyed limiter to a user-keyed one here.
    """
    monkeypatch.setattr(deps, "get_settings", lambda: _FakeSettings())

    first_user_headers = registered_user["headers"]
    for _ in range(2):
        assert (await client.get("/v1/sessions", headers=first_user_headers)).status_code == 200
    assert (await client.get("/v1/sessions", headers=first_user_headers)).status_code == 429

    register_response = await client.post(
        "/v1/auth/register",
        json={
            "email": "ratelimit-second-user@example.com",
            "username": "ratelimit_second_user",
            "password": "test12345",
        },
    )
    assert register_response.status_code == 201
    second_user_headers = {
        "Authorization": f"Bearer {register_response.json()['tokens']['access_token']}"
    }

    response = await client.get("/v1/sessions", headers=second_user_headers)
    assert response.status_code == 200


async def test_general_rate_limit_fails_open_when_redis_unavailable(
    client: AsyncClient, registered_user: dict, app
):
    app.dependency_overrides[get_redis] = lambda: _AlwaysFailsRedis()

    response = await client.get("/v1/sessions", headers=registered_user["headers"])

    assert response.status_code == 200
