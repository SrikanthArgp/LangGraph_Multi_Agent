import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ChatSession


async def get_session(
    db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID
) -> ChatSession | None:
    """Ownership-checked lookup - callers never need to duplicate the user_id filter
    (a session that exists but belongs to another user looks identical to a missing one).
    """
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def list_sessions(
    db: AsyncSession, user_id: uuid.UUID, *, limit: int = 5, include_archived: bool = False
) -> list[ChatSession]:
    stmt = select(ChatSession).where(ChatSession.user_id == user_id)
    if not include_archived:
        stmt = stmt.where(ChatSession.is_archived.is_(False))
    stmt = stmt.order_by(ChatSession.last_message_at.desc().nulls_last()).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create_session(
    db: AsyncSession, user_id: uuid.UUID, title: str | None = None
) -> ChatSession:
    session = ChatSession(user_id=user_id, title=title)
    db.add(session)
    await db.flush()
    await db.refresh(session)
    return session


async def update_title(db: AsyncSession, session: ChatSession, title: str) -> ChatSession:
    session.title = title
    await db.flush()
    await db.refresh(session)
    return session


async def archive_session(db: AsyncSession, session: ChatSession) -> ChatSession:
    session.is_archived = True
    await db.flush()
    await db.refresh(session)
    return session


async def touch_last_message_at(
    db: AsyncSession, session: ChatSession, when: datetime | None = None
) -> ChatSession:
    session.last_message_at = when or datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(session)
    return session
