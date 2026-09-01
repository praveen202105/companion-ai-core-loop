from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from companion.domain import (
    MemoryEventView,
    MemoryStatus,
    MessageView,
    SessionView,
    StoredMemory,
)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    request_id: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9._:-]+$")
    message: str = Field(min_length=1, max_length=4_000)


class SessionResponse(BaseModel):
    session: SessionView


class MessagesResponse(BaseModel):
    messages: list[MessageView]


class MemoriesResponse(BaseModel):
    status: MemoryStatus
    memories: list[StoredMemory]
    events: list[MemoryEventView]


class HealthResponse(BaseModel):
    status: str
    checks: dict[str, Any] = Field(default_factory=dict)
