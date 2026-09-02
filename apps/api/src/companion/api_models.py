from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from companion.domain import (
    MemoryStatus,
    MessageView,
    SessionView,
)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    request_id: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9._:-]+$")
    message: str = Field(min_length=1, max_length=4_000)


class UserChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9._:-]+$")
    message: str = Field(min_length=1, max_length=4_000)


class AuthenticatedPrincipal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auth_provider: Literal["google"]
    auth_subject: str = Field(min_length=1, max_length=255)


class SessionResponse(BaseModel):
    session: SessionView


class MessagesResponse(BaseModel):
    messages: list[MessageView]


class UserSessionResponse(BaseModel):
    session: SessionView
    messages: list[MessageView]


class MemoryInspectorItem(BaseModel):
    id: UUID
    canonical_key: str
    memory_type: str
    normalized_text: str
    value: str
    status: MemoryStatus
    confidence: float
    importance: float


class MemoryEventItem(BaseModel):
    id: UUID
    action: str
    canonical_key: str | None
    reason_code: str
    created_at: str


class RetrievalInspectorTrace(BaseModel):
    algorithm_version: str
    candidate_count: int
    selected: list[dict[str, Any]]
    degraded_mode: str | None


class MemoriesResponse(BaseModel):
    status: MemoryStatus
    memories: list[MemoryInspectorItem]
    events: list[MemoryEventItem]
    trace: RetrievalInspectorTrace | None


class HealthResponse(BaseModel):
    status: str
    checks: dict[str, Any] = Field(default_factory=dict)
