import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.requires_db


async def test_create_and_get_session(client: AsyncClient, registered_user: dict):
    created = await client.post(
        "/v1/sessions", headers=registered_user["headers"], json={"title": "My chat"}
    )
    assert created.status_code == 201
    session_id = created.json()["id"]
    assert created.json()["title"] == "My chat"
    assert created.json()["is_archived"] is False

    fetched = await client.get(f"/v1/sessions/{session_id}", headers=registered_user["headers"])
    assert fetched.status_code == 200
    assert fetched.json()["id"] == session_id


async def test_list_sessions_returns_created_session(client: AsyncClient, registered_user: dict):
    created = await client.post(
        "/v1/sessions", headers=registered_user["headers"], json={"title": "Listed chat"}
    )
    session_id = created.json()["id"]

    listed = await client.get("/v1/sessions", headers=registered_user["headers"])
    assert listed.status_code == 200
    ids = [s["id"] for s in listed.json()["sessions"]]
    assert session_id in ids

    # Second call should hit the Redis-cache path (same code, same result) - see the Phase 6
    # smoke test note in completed.md about the empty-session ZSET consistency fix.
    listed_again = await client.get("/v1/sessions", headers=registered_user["headers"])
    assert listed_again.status_code == 200
    assert [s["id"] for s in listed_again.json()["sessions"]] == ids


async def test_rename_session(client: AsyncClient, registered_user: dict):
    created = await client.post(
        "/v1/sessions", headers=registered_user["headers"], json={"title": "Original"}
    )
    session_id = created.json()["id"]

    renamed = await client.patch(
        f"/v1/sessions/{session_id}", headers=registered_user["headers"], json={"title": "Renamed"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Renamed"


async def test_delete_session_archives_and_hides_from_listing(
    client: AsyncClient, registered_user: dict
):
    created = await client.post(
        "/v1/sessions", headers=registered_user["headers"], json={"title": "To delete"}
    )
    session_id = created.json()["id"]

    deleted = await client.delete(
        f"/v1/sessions/{session_id}", headers=registered_user["headers"]
    )
    assert deleted.status_code == 204

    listed = await client.get("/v1/sessions", headers=registered_user["headers"])
    assert session_id not in [s["id"] for s in listed.json()["sessions"]]

    # Still directly fetchable by ID (soft-delete, not gone) - a real client, not a stray
    # user, should still be able to see their own archived session by ID.
    fetched = await client.get(f"/v1/sessions/{session_id}", headers=registered_user["headers"])
    assert fetched.status_code == 200
    assert fetched.json()["is_archived"] is True


async def test_session_not_found_returns_404(client: AsyncClient, registered_user: dict):
    response = await client.get(
        "/v1/sessions/00000000-0000-0000-0000-000000000000",
        headers=registered_user["headers"],
    )
    assert response.status_code == 404


async def test_ownership_enforced_across_users(client: AsyncClient, registered_user: dict):
    other_email = f"owner-check_{uuid.uuid4().hex[:12]}@example.com"
    other_email_response = await client.post(
        "/v1/auth/register",
        json={"email": other_email, "username": f"owner_{uuid.uuid4().hex[:8]}", "password": "test12345"},
    )
    assert other_email_response.status_code == 201
    other_headers = {
        "Authorization": f"Bearer {other_email_response.json()['tokens']['access_token']}"
    }

    created = await client.post(
        "/v1/sessions", headers=registered_user["headers"], json={"title": "User A's session"}
    )
    session_id = created.json()["id"]

    # User B can't read, rename, or delete user A's session
    get_resp = await client.get(f"/v1/sessions/{session_id}", headers=other_headers)
    assert get_resp.status_code == 404

    patch_resp = await client.patch(
        f"/v1/sessions/{session_id}", headers=other_headers, json={"title": "Hijacked"}
    )
    assert patch_resp.status_code == 404

    delete_resp = await client.delete(f"/v1/sessions/{session_id}", headers=other_headers)
    assert delete_resp.status_code == 404

    # User A's session is untouched
    still_there = await client.get(f"/v1/sessions/{session_id}", headers=registered_user["headers"])
    assert still_there.status_code == 200
    assert still_there.json()["title"] == "User A's session"
