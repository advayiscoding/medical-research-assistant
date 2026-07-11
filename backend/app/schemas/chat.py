"""Chat API schemas — sessions, messages, and the ask-in-session response."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.rag import Citation


class SessionRead(BaseModel):
    # UUID (not str) so model_validate() coerces straight from the ORM object;
    # JSON serialization emits the same canonical string either way.
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class MessageRead(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime
    citations: list[Citation] = Field(default_factory=list)


class SessionDetail(SessionRead):
    messages: list[MessageRead] = Field(default_factory=list)


class PostMessageRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=12)


class PostMessageResponse(BaseModel):
    session_id: str
    user_message: MessageRead
    assistant_message: MessageRead
    insufficient_evidence: bool
