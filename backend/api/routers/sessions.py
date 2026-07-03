import uuid
from datetime import datetime

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user, get_db, get_redis
from api.schemas.session import SessionCreate, SessionListResponse, SessionPatch, SessionResponse
from cache.exceptions import CacheUnavailableError
from cache.sessions import (
    add_session_to_listing,
    get_recent_sessions,
    get_session_meta,
    set_session_meta,
)
from db.crud import sessions as sessions_crud
from db.models import ChatSession, User

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _to_response(session: ChatSession) -> SessionResponse:
    return SessionResponse.model_validate(session)


async def cache_session(redis: aioredis.Redis, session: ChatSession) -> None:
    """Best-effort write-through to both Redis structures (A: listing ZSET, B: meta HASH).
    Swallows CacheUnavailableError - a Redis outage degrades reads to DB-only, it should
    never fail the write that already succeeded in Postgres. Public (not `_`-prefixed) since
    api/routers/chat.py also calls this after touch_last_message_at - both routers mutate
    session state and both need to keep the cache from going stale, not just this one.

    Deviation from plan.md's literal HASH B field list: also stores `updated_at`, not just
    the 5 documented fields. Without it, a cache-hit hydration in list_sessions() below has
    no value for SessionResponse.updated_at (the DB model has it, the plan's HASH schema
    didn't). Cheap, self-contained addition - one more HSET field, same TTL.

    Also deviates from a literal reading of the ZSET write in plan.md's Redis Data Model:
    always adds to the listing, scored by `last_message_at or created_at` instead of skipping
    the ZSET write entirely for a session with no messages yet. A strict reading (only score
    by last_message_at, which is nullable) would mean a freshly created, message-less session
    is included in the DB-fallback listing (ORDER BY ... NULLS LAST) but then silently vanishes
    from every subsequent cache-hit listing, since it was never a ZSET member in the first
    place - confirmed by hitting this exact inconsistency during the Phase 6 manual smoke test.
    """
    try:
        await set_session_meta(
            redis,
            session.id,
            title=session.title or "",
            user_id=str(session.user_id),
            created_at=session.created_at.isoformat(),
            updated_at=session.updated_at.isoformat(),
            last_message_at=session.last_message_at.isoformat() if session.last_message_at else "",
            is_archived="1" if session.is_archived else "0",
        )
        await add_session_to_listing(
            redis, session.user_id, session.id, session.last_message_at or session.created_at
        )
    except CacheUnavailableError:
        pass


def _parse_cached_session(session_id: str, meta: dict) -> SessionResponse | None:
    try:
        created_at = datetime.fromisoformat(meta["created_at"])
        return SessionResponse(
            id=uuid.UUID(session_id),
            user_id=uuid.UUID(meta["user_id"]),
            title=meta.get("title") or None,
            is_archived=meta.get("is_archived") == "1",
            last_message_at=(
                datetime.fromisoformat(meta["last_message_at"])
                if meta.get("last_message_at")
                else None
            ),
            created_at=created_at,
            updated_at=(
                datetime.fromisoformat(meta["updated_at"]) if meta.get("updated_at") else created_at
            ),
        )
    except (KeyError, ValueError):
        return None


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> SessionListResponse:
    try:
        cached_ids = await get_recent_sessions(redis, current_user.id)
    except CacheUnavailableError:
        cached_ids = []

    sessions: list[SessionResponse] = []
    if cached_ids:
        for session_id in cached_ids:
            try:
                meta = await get_session_meta(redis, session_id)
            except CacheUnavailableError:
                meta = {}
            parsed = _parse_cached_session(session_id, meta) if meta else None
            if parsed is None:
                sessions = []  # partial/stale cache hit - fall through to DB for consistency
                break
            sessions.append(parsed)

    if not sessions:
        db_sessions = await sessions_crud.list_sessions(db, current_user.id)
        for db_session in db_sessions:
            await cache_session(redis, db_session)
        sessions = [_to_response(s) for s in db_sessions]

    sessions = [s for s in sessions if not s.is_archived]
    return SessionListResponse(sessions=sessions)


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: SessionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> SessionResponse:
    session = await sessions_crud.create_session(db, current_user.id, payload.title)
    await cache_session(redis, session)
    return _to_response(session)


async def _get_owned_session_or_404(
    db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID
) -> ChatSession:
    session = await sessions_crud.get_session(db, session_id, user_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    session = await _get_owned_session_or_404(db, session_id, current_user.id)
    return _to_response(session)


@router.patch("/{session_id}", response_model=SessionResponse)
async def rename_session(
    session_id: uuid.UUID,
    payload: SessionPatch,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> SessionResponse:
    session = await _get_owned_session_or_404(db, session_id, current_user.id)
    session = await sessions_crud.update_title(db, session, payload.title)
    await cache_session(redis, session)
    return _to_response(session)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> None:
    """Soft-delete: is_archived=True, matching plan.md's DELETE semantics."""
    session = await _get_owned_session_or_404(db, session_id, current_user.id)
    session = await sessions_crud.archive_session(db, session)
    await cache_session(redis, session)
