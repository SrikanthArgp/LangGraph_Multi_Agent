import uuid

import pytest
from httpx import AsyncClient
from langgraph.checkpoint.memory import MemorySaver

from api.dependencies import get_graph
from multi_agent.graph import create_app
from tests.conftest import FailingGraph, FakeGraph

pytestmark = pytest.mark.requires_db


async def _create_session(client: AsyncClient, headers: dict) -> str:
    response = await client.post("/v1/sessions", headers=headers, json={"title": "Chat test"})
    assert response.status_code == 201
    return response.json()["id"]


async def test_send_message_persists_and_returns_both_messages(
    client: AsyncClient, registered_user: dict, fake_graph: FakeGraph
):
    session_id = await _create_session(client, registered_user["headers"])

    response = await client.post(
        f"/v1/sessions/{session_id}/messages",
        headers=registered_user["headers"],
        json={"question": "What is CRAG?"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["question_message"]["content"] == "What is CRAG?"
    assert body["question_message"]["role"] == "user"
    assert body["answer_message"]["content"] == fake_graph.generation
    assert body["answer_message"]["role"] == "assistant"
    assert len(fake_graph.calls) == 1
    assert fake_graph.calls[0]["config"]["configurable"]["thread_id"] == session_id

    history = await client.get(
        f"/v1/sessions/{session_id}/messages", headers=registered_user["headers"]
    )
    assert history.status_code == 200
    roles = [m["role"] for m in history.json()["messages"]]
    assert roles == ["user", "assistant"]


async def test_send_message_session_not_found_returns_404(
    client: AsyncClient, registered_user: dict
):
    response = await client.post(
        "/v1/sessions/00000000-0000-0000-0000-000000000000/messages",
        headers=registered_user["headers"],
        json={"question": "hello"},
    )
    assert response.status_code == 404


async def test_send_message_ownership_enforced(client: AsyncClient, registered_user: dict):
    session_id = await _create_session(client, registered_user["headers"])

    other_email = f"chatowner_{uuid.uuid4().hex[:12]}@example.com"
    other = await client.post(
        "/v1/auth/register",
        json={
            "email": other_email,
            "username": f"chatowner_{uuid.uuid4().hex[:8]}",
            "password": "test12345",
        },
    )
    other_headers = {"Authorization": f"Bearer {other.json()['tokens']['access_token']}"}

    response = await client.post(
        f"/v1/sessions/{session_id}/messages",
        headers=other_headers,
        json={"question": "not yours"},
    )
    assert response.status_code == 404


async def test_send_message_graph_failure_returns_502(
    client: AsyncClient, registered_user: dict, app
):
    session_id = await _create_session(client, registered_user["headers"])

    async def _get_failing_graph():
        yield FailingGraph()

    app.dependency_overrides[get_graph] = _get_failing_graph

    response = await client.post(
        f"/v1/sessions/{session_id}/messages",
        headers=registered_user["headers"],
        json={"question": "this will fail"},
    )
    assert response.status_code == 502
    assert response.json() == {"detail": "The assistant failed to produce an answer, please try again"}


async def test_stream_message_happy_path(client: AsyncClient, registered_user: dict, fake_graph):
    session_id = await _create_session(client, registered_user["headers"])

    async with client.stream(
        "GET",
        f"/v1/sessions/{session_id}/stream",
        headers=registered_user["headers"],
        params={"question": "stream this"},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join([chunk async for chunk in response.aiter_text()])

    assert '"type": "token"' in body
    assert '"type": "done"' in body
    assert fake_graph.generation in body


async def test_stream_message_graph_failure_emits_error_event(
    client: AsyncClient, registered_user: dict, app
):
    session_id = await _create_session(client, registered_user["headers"])

    async def _get_failing_graph():
        yield FailingGraph()

    app.dependency_overrides[get_graph] = _get_failing_graph

    async with client.stream(
        "GET",
        f"/v1/sessions/{session_id}/stream",
        headers=registered_user["headers"],
        params={"question": "this will fail"},
    ) as response:
        assert response.status_code == 200  # SSE already committed to a 200 stream
        body = "".join([chunk async for chunk in response.aiter_text()])

    assert '"type": "error"' in body


@pytest.mark.integration
async def test_send_message_real_graph_end_to_end(
    client: AsyncClient, registered_user: dict, app
):
    """Runs the actual compiled CRAG graph (real OpenAI/Tavily calls) through the API, with a
    MemorySaver instead of AsyncPostgresSaver so it doesn't need the Postgres connection pool
    api/main.py's lifespan normally provides - the graph itself is identical either way, only
    the checkpointer backing differs.
    """
    real_graph = create_app(MemorySaver())

    async def _get_real_graph():
        yield real_graph

    app.dependency_overrides[get_graph] = _get_real_graph

    session_id = await _create_session(client, registered_user["headers"])
    response = await client.post(
        f"/v1/sessions/{session_id}/messages",
        headers=registered_user["headers"],
        json={"question": "What are the types of agent memory?"},
        timeout=60,
    )
    assert response.status_code == 201
    answer = response.json()["answer_message"]["content"]
    assert len(answer) > 0
