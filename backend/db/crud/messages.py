import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Message


async def create_message(
    db: AsyncSession,
    session_id: uuid.UUID,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> Message:
    message = Message(session_id=session_id, role=role, content=content, metadata_=metadata)
    db.add(message)
    await db.flush()
    await db.refresh(message)
    return message


async def list_messages_for_session(
    db: AsyncSession, session_id: uuid.UUID, *, limit: int = 50, offset: int = 0
) -> list[Message]:
    stmt = (
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
