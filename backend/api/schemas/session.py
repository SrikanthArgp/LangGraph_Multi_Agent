import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=500)


class SessionPatch(BaseModel):
    title: str = Field(max_length=500)


class SessionResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    user_id: uuid.UUID
    title: str | None
    is_archived: bool
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SessionListResponse(BaseModel):
    sessions: list[SessionResponse]
