import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class MessageResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    metadata: dict[str, Any] | None = Field(validation_alias="metadata_", default=None)
    created_at: datetime


class ChatResponse(BaseModel):
    question_message: MessageResponse
    answer_message: MessageResponse


class MessagesListResponse(BaseModel):
    messages: list[MessageResponse]


# SSE event payloads (application/json per event) - see plan.md "API Endpoints"


class TokenEvent(BaseModel):
    type: Literal["token"] = "token"
    token: str


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"
    message_id: uuid.UUID


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    detail: str
