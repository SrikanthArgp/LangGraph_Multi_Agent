import json
import logging
import uuid
from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user, get_db, get_graph, get_redis
from api.routers.sessions import cache_session
from api.schemas.chat import ChatRequest, ChatResponse, MessageResponse, MessagesListResponse
from cache.exceptions import CacheUnavailableError
from cache.sessions import push_message
from db.crud import messages as messages_crud
from db.crud import sessions as sessions_crud
from db.models import ChatSession, Message, User
from multi_agent.observability.langfuse_client import get_langfuse_handler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["chat"])


async def _get_owned_session_or_404(
    db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID
) -> ChatSession:
    session = await sessions_crud.get_session(db, session_id, user_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


def _graph_config(session_id: uuid.UUID) -> dict:
    callbacks = []
    handler = get_langfuse_handler()
    if handler is not None:
        callbacks.append(handler)
    return {"configurable": {"thread_id": str(session_id)}, "callbacks": callbacks}


async def _cache_new_messages(
    redis: aioredis.Redis, session: ChatSession, *new_messages: Message
) -> None:
    try:
        for message in new_messages:
            await push_message(
                redis,
                session.id,
                {
                    "id": str(message.id),
                    "role": message.role,
                    "content": message.content,
                    "created_at": message.created_at.isoformat(),
                },
            )
    except CacheUnavailableError:
        pass  # best-effort - the DB write already succeeded


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@router.get("/{session_id}/messages", response_model=MessagesListResponse)
async def list_messages(
    session_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessagesListResponse:
    await _get_owned_session_or_404(db, session_id, current_user.id)
    rows = await messages_crud.list_messages_for_session(db, session_id, limit=limit, offset=offset)
    return MessagesListResponse(messages=[MessageResponse.model_validate(m) for m in rows])


@router.post(
    "/{session_id}/messages", response_model=ChatResponse, status_code=status.HTTP_201_CREATED
)
async def send_message(
    session_id: uuid.UUID,
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    graph=Depends(get_graph),
) -> ChatResponse:
    session = await _get_owned_session_or_404(db, session_id, current_user.id)
    question_message = await messages_crud.create_message(db, session.id, "user", payload.question)

    try:
        result = await graph.ainvoke(
            {"question": payload.question}, config=_graph_config(session.id)
        )
    except Exception as e:
        logger.warning("chat_generation_failed", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The assistant failed to produce an answer, please try again",
        ) from e

    answer_message = await messages_crud.create_message(
        db,
        session.id,
        "assistant",
        result.get("generation") or "",
        metadata={"web_search": bool(result.get("web_search", False))},
    )
    session = await sessions_crud.touch_last_message_at(db, session)
    await cache_session(redis, session)
    await _cache_new_messages(redis, session, question_message, answer_message)

    return ChatResponse(
        question_message=MessageResponse.model_validate(question_message),
        answer_message=MessageResponse.model_validate(answer_message),
    )


@router.get("/{session_id}/stream")
async def stream_message(
    session_id: uuid.UUID,
    question: str = Query(min_length=1, max_length=4000),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    graph=Depends(get_graph),
) -> StreamingResponse:
    """SSE token stream.

    NOTE (known limitation, not silently glossed over): the CRAG graph's generate() node
    (nodes/generate.py) calls the LLM via a synchronous, tenacity-wrapped `.invoke()` inside
    a plain (non-async) node function - there is no per-token event source available to relay.
    This endpoint therefore runs the graph to completion first, then emits the full answer as
    a single `token` event followed by `done` - not true incremental streaming. The SSE event
    contract (`token`/`done`/`error`) is exactly what a real streaming implementation would
    use, so Phase 8's frontend won't need to change when real token streaming is wired in
    (would require reworking generate()'s LLM call to stream and restructuring this endpoint
    to consume it as it arrives - tracked as follow-up in completed.md, out of scope for this
    router-only phase).

    All DB/graph work happens before StreamingResponse is constructed, deliberately - a
    yield-dependency (like `db` here) torn down while a StreamingResponse body is still being
    read is a well-known FastAPI footgun. Since there's no incremental work to do inside the
    generator anyway (see above), the generator only yields pre-computed strings.
    """
    session = await _get_owned_session_or_404(db, session_id, current_user.id)
    question_message = await messages_crud.create_message(db, session.id, "user", question)

    try:
        result = await graph.ainvoke({"question": question}, config=_graph_config(session.id))
    except Exception:
        logger.warning("chat_stream_generation_failed", exc_info=True)

        async def error_stream() -> AsyncGenerator[str, None]:
            yield _sse(
                {
                    "type": "error",
                    "detail": "The assistant failed to produce an answer, please try again",
                }
            )

        return StreamingResponse(error_stream(), media_type="text/event-stream")

    answer_content = result.get("generation") or ""
    answer_message = await messages_crud.create_message(
        db,
        session.id,
        "assistant",
        answer_content,
        metadata={"web_search": bool(result.get("web_search", False))},
    )
    session = await sessions_crud.touch_last_message_at(db, session)
    await cache_session(redis, session)
    await _cache_new_messages(redis, session, question_message, answer_message)

    async def event_stream() -> AsyncGenerator[str, None]:
        yield _sse({"type": "token", "token": answer_content})
        yield _sse({"type": "done", "message_id": str(answer_message.id)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
