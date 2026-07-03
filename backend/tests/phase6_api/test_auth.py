import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.requires_db


async def test_register_returns_tokens_and_user(client: AsyncClient):
    email = f"test_{uuid.uuid4().hex[:12]}@example.com"
    response = await client.post(
        "/v1/auth/register",
        json={"email": email, "username": "newuser", "password": "test12345"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == email
    assert body["tokens"]["token_type"] == "bearer"
    assert body["tokens"]["expires_in"] == 900


async def test_duplicate_register_returns_409(client: AsyncClient, registered_user: dict):
    response = await client.post(
        "/v1/auth/register",
        json={
            "email": registered_user["email"],
            "username": "someone_else",
            "password": "test12345",
        },
    )
    assert response.status_code == 409


async def test_login_success(client: AsyncClient, registered_user: dict):
    response = await client.post(
        "/v1/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()["tokens"]


async def test_login_wrong_password_returns_401(client: AsyncClient, registered_user: dict):
    response = await client.post(
        "/v1/auth/login",
        json={"email": registered_user["email"], "password": "wrong-password"},
    )
    assert response.status_code == 401


async def test_me_requires_valid_token(client: AsyncClient, registered_user: dict):
    ok = await client.get("/v1/auth/me", headers=registered_user["headers"])
    assert ok.status_code == 200
    assert ok.json()["email"] == registered_user["email"]

    unauthorized = await client.get("/v1/auth/me")
    assert unauthorized.status_code == 401

    bad_token = await client.get("/v1/auth/me", headers={"Authorization": "Bearer garbage"})
    assert bad_token.status_code == 401


async def test_refresh_rotates_and_revokes_old_token(client: AsyncClient, registered_user: dict):
    refresh_token = registered_user["tokens"]["refresh_token"]

    first = await client.post("/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert first.status_code == 200
    new_access = first.json()["access_token"]
    assert new_access != registered_user["tokens"]["access_token"]

    reuse = await client.post("/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert reuse.status_code == 401

    me = await client.get("/v1/auth/me", headers={"Authorization": f"Bearer {new_access}"})
    assert me.status_code == 200


async def test_logout_revokes_access_token(client: AsyncClient, registered_user: dict):
    logout = await client.post(
        "/v1/auth/logout", headers=registered_user["headers"], json={}
    )
    assert logout.status_code == 204

    me = await client.get("/v1/auth/me", headers=registered_user["headers"])
    assert me.status_code == 401


async def test_auth_rate_limit_returns_429(client: AsyncClient):
    """IP-keyed bucket (default RATE_LIMIT_AUTH_PER_MINUTE=10), shared across register/login -
    all requests in this test look like the same client under httpx.ASGITransport's fixed
    default client address, so this exercises the real bucket rather than mocking it.
    """
    responses = []
    for _ in range(12):
        responses.append(
            await client.post(
                "/v1/auth/login", json={"email": "nobody@example.com", "password": "x"}
            )
        )
    statuses = [r.status_code for r in responses]
    assert 429 in statuses, statuses
    assert statuses[:10].count(429) == 0  # first 10 shouldn't be rate-limited yet
