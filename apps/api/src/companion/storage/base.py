from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol
from uuid import UUID

from companion.domain import (
    MemoryAction,
    MemoryCandidate,
    MemoryEventView,
    RetrievalTraceView,
    StoredMemory,
)


class MemoryStore(Protocol):
    def add_memory(
        self,
        *,
        session_id: UUID,
        candidate: MemoryCandidate,
        source_message_id: UUID | None = None,
        embedding: list[float] | None = None,
    ) -> StoredMemory: ...

    def active_memory(self, session_id: UUID, key: str) -> StoredMemory | None: ...

    def update_memory(
        self,
        *,
        memory_id: UUID,
        candidate: MemoryCandidate,
        source_message_id: UUID | None,
        reason_code: str,
        embedding: list[float] | None = None,
    ) -> StoredMemory: ...

    def supersede_memory(
        self,
        *,
        old_memory_id: UUID,
        candidate: MemoryCandidate,
        source_message_id: UUID | None,
        embedding: list[float] | None = None,
        reason_code: str = "changed_current_truth",
    ) -> StoredMemory: ...

    def record_event(
        self,
        *,
        session_id: UUID,
        action: MemoryAction,
        reason_code: str,
        memory_id: UUID | None = None,
        source_message_id: UUID | None = None,
        key: str | None = None,
        previous: dict[str, Any] | None = None,
        candidate: dict[str, Any] | None = None,
    ) -> MemoryEventView: ...

    def search_lexical(
        self,
        *,
        session_id: UUID,
        query: str,
        limit: int = 20,
    ) -> list[StoredMemory]: ...

    def search_vector(
        self,
        *,
        session_id: UUID,
        query_embedding: list[float],
        limit: int = 20,
    ) -> list[StoredMemory]: ...

    def mark_memories_accessed(self, memory_ids: Iterable[UUID]) -> None: ...

    def record_retrieval(
        self,
        *,
        session_id: UUID,
        query: str,
        candidate_count: int,
        selected: list[dict[str, Any]],
        message_id: UUID | None = None,
        algorithm_version: str = "rrf-v1",
        degraded_mode: str | None = None,
    ) -> RetrievalTraceView: ...
