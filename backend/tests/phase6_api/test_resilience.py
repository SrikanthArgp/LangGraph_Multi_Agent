import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import api.dependencies as deps
from api.dependencies import get_db
from auth.dependencies import get_db_session

pytestmark = pytest.mark.requires_db


async def test_get_db_translates_connection_error_to_503(monkeypatch):
    """Unit-tests the real get_db() generator directly (not through the HTTP stack) against
    an engine pointed at an unreachable host - see api/dependencies.py's OperationalError
    branch. Session construction is lazy (no connection attempt yet), so the failure only
    surfaces once a query actually runs.

    get_db's try/except wraps `yield session`, not arbitrary code the caller runs after
    obtaining the session - so replicating what FastAPI actually does when a router raises is
    exactly `gen.athrow(...)`, injecting the exception at the yield point (this is what
    AsyncExitStack.__aexit__ does for a generator-based yield dependency), not just calling
    `gen.__anext__()` again.
    """
    broken_engine = create_async_engine(
        "postgresql+psycopg://baduser:badpass@127.0.0.1:1/nonexistent",
        pool_pre_ping=False,
        connect_args={"connect_timeout": 2},
    )
    broken_factory = async_sessionmaker(broken_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(deps, "async_session_factory", broken_factory)

    gen = get_db()
    session = await gen.__anext__()
    try:
        await session.execute(text("SELECT 1"))
        pytest.fail("expected OperationalError from the broken engine, connection unexpectedly succeeded")
    except OperationalError as original_exc:
        with pytest.raises(HTTPException) as exc_info:
            await gen.athrow(type(original_exc), original_exc, original_exc.__traceback__)
        assert exc_info.value.status_code == 503
    finally:
        await broken_engine.dispose()


async def test_unhandled_non_http_exception_returns_generic_500_envelope(
    client: AsyncClient, registered_user: dict, app
):
    """Simulates 'something else still raised' (plan.md's Phase 6 failure-path wording) -
    not an OperationalError (that's the 503 case above) and not something a router catches
    itself. Asserts the global handler's consistent {"detail": ...} shape, not a leaked
    traceback.
    """

    async def _broken_get_db():
        raise RuntimeError("simulated unexpected failure, unrelated to a DB connection")
        yield  # pragma: no cover - unreachable, keeps this a generator function

    app.dependency_overrides[get_db] = _broken_get_db
    app.dependency_overrides[get_db_session] = _broken_get_db

    response = await client.get("/v1/sessions", headers=registered_user["headers"])
    assert response.status_code == 500
    assert response.json() == {"detail": "internal server error"}


async def test_request_id_header_present_on_every_response(client: AsyncClient):
    response = await client.get("/health")
    assert "x-request-id" in response.headers
