import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from db.models import ChatSession, Message, RefreshToken, User

pytestmark = pytest.mark.requires_db


def _unique_email() -> str:
    return f"healthcheck-{uuid.uuid4().hex[:8]}@example.com"


def _unique_username() -> str:
    return f"healthcheck-{uuid.uuid4().hex[:8]}"


async def test_create_user_generates_id_and_defaults(db_session):
    user = User(email=_unique_email(), username=_unique_username(), hashed_password="hashed")
    db_session.add(user)
    await db_session.flush()

    assert user.id is not None
    assert user.created_at is not None
    assert user.is_active is True


async def test_duplicate_email_violates_unique_constraint(db_session):
    email = _unique_email()
    db_session.add(User(email=email, username=_unique_username(), hashed_password="x"))
    await db_session.flush()

    db_session.add(User(email=email, username=_unique_username(), hashed_password="x"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_chat_session_relationship_round_trip(db_session):
    user = User(email=_unique_email(), username=_unique_username(), hashed_password="x")
    db_session.add(user)
    await db_session.flush()

    session = ChatSession(user_id=user.id, title="test session")
    db_session.add(session)
    await db_session.flush()
    await db_session.refresh(user, attribute_names=["sessions"])

    assert len(user.sessions) == 1
    assert user.sessions[0].id == session.id


async def test_message_role_check_constraint_rejects_invalid_role(db_session):
    user = User(email=_unique_email(), username=_unique_username(), hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    session = ChatSession(user_id=user.id)
    db_session.add(session)
    await db_session.flush()

    db_session.add(Message(session_id=session.id, role="not-a-role", content="hi"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_message_metadata_jsonb_round_trip(db_session):
    user = User(email=_unique_email(), username=_unique_username(), hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    session = ChatSession(user_id=user.id)
    db_session.add(session)
    await db_session.flush()

    message = Message(
        session_id=session.id,
        role="assistant",
        content="hi",
        metadata_={"routed": "vectorstore", "web_search": False},
    )
    db_session.add(message)
    await db_session.flush()
    await db_session.refresh(message)

    assert message.metadata_ == {"routed": "vectorstore", "web_search": False}


async def test_deleting_user_cascades_to_sessions_and_refresh_tokens(db_session):
    user = User(email=_unique_email(), username=_unique_username(), hashed_password="x")
    db_session.add(user)
    await db_session.flush()

    session = ChatSession(user_id=user.id)
    token = RefreshToken(
        user_id=user.id,
        token_hash="hash",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db_session.add_all([session, token])
    await db_session.flush()
    session_id, token_id = session.id, token.id

    await db_session.delete(user)
    await db_session.flush()

    orphaned_session = await db_session.execute(select(ChatSession).where(ChatSession.id == session_id))
    orphaned_token = await db_session.execute(select(RefreshToken).where(RefreshToken.id == token_id))
    assert orphaned_session.scalar_one_or_none() is None
    assert orphaned_token.scalar_one_or_none() is None
