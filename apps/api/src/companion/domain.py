from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class MemoryOwner(StrEnum):
    USER = "user"
    COMPANION = "companion"


class MemoryType(StrEnum):
    PROFILE = "profile"
    PREFERENCE = "preference"
    STATE = "state"
    EVENT = "event"
    PLAN = "plan"


class MemoryStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"


class MemoryAction(StrEnum):
    ADD = "add"
    UPDATE = "update"
    SUPERSEDE = "supersede"
    IGNORE = "ignore"
    EXTRACTION_FAILED = "extraction_failed"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class MemoryCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    should_store: bool = True
    owner: MemoryOwner = MemoryOwner.USER
    memory_type: MemoryType
    subject: str = Field(min_length=1, max_length=120)
    predicate: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=2_000)
    normalized_text: str = Field(min_length=1, max_length=4_000)
    confidence: float = Field(ge=0, le=1)
    importance: float = Field(ge=0, le=1)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    expires_at: datetime | None = None


class StoredMemory(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    owner: MemoryOwner
    memory_type: MemoryType
    subject: str
    predicate: str
    value: str
    canonical_key: str
    normalized_text: str
    status: MemoryStatus
    confidence: float
    importance: float
    valid_from: datetime | None
    valid_to: datetime | None
    expires_at: datetime | None
    source_message_id: UUID | None
    superseded_by_id: UUID | None
    embedding: list[float] | None
    access_count: int
    created_at: datetime
    updated_at: datetime
    last_accessed_at: datetime | None


class MemoryEventView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    memory_id: UUID | None
    source_message_id: UUID | None
    action: MemoryAction
    canonical_key: str | None
    previous_snapshot: dict[str, Any] | None
    candidate_snapshot: dict[str, Any] | None
    reason_code: str
    created_at: datetime


class MessageView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    sequence_no: int
    role: MessageRole
    content: str
    request_id: str | None
    reply_to_request_id: str | None
    model: str | None
    prompt_version: str | None
    input_tokens: int | None
    output_tokens: int | None
    created_at: datetime


class SessionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    persona_version: str
    created_at: datetime
    last_activity_at: datetime
    expires_at: datetime


class RetrievalTraceView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    message_id: UUID | None
    query: str
    algorithm_version: str
    candidate_count: int
    selected: list[dict[str, Any]]
    degraded_mode: str | None
    created_at: datetime
