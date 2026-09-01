from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from companion.domain import MemoryType, RetrievalTraceView, StoredMemory
from companion.embeddings import EmbeddingProvider
from companion.storage import MemoryStore


class RetrievedMemory(BaseModel):
    memory: StoredMemory
    score: float
    factors: dict[str, float]


class RetrievalResult(BaseModel):
    memories: list[RetrievedMemory] = Field(default_factory=list)
    trace: RetrievalTraceView


class Retriever:
    def __init__(
        self,
        store: MemoryStore,
        embedding_provider: EmbeddingProvider,
        *,
        rrf_k: int = 60,
    ) -> None:
        self.store = store
        self.embedding_provider = embedding_provider
        self.rrf_k = rrf_k

    def retrieve(
        self,
        query: str,
        session_id: UUID,
        *,
        top_k: int = 6,
        now: datetime | None = None,
        message_id: UUID | None = None,
    ) -> RetrievalResult:
        lexical = self.store.search_lexical(
            session_id=session_id,
            query=query,
            limit=20,
        )
        degraded_mode: str | None = None
        try:
            query_embedding = self.embedding_provider.embed_one(query)
            vector = self.store.search_vector(
                session_id=session_id,
                query_embedding=query_embedding,
                limit=20,
            )
        except Exception:
            vector = []
            degraded_mode = "lexical_only"

        combined: dict[UUID, StoredMemory] = {
            memory.id: memory for memory in [*lexical, *vector]
        }
        lexical_rank = {memory.id: rank for rank, memory in enumerate(lexical, start=1)}
        vector_rank = {memory.id: rank for rank, memory in enumerate(vector, start=1)}
        scored = [
            self._score(
                memory,
                query=query,
                lexical_rank=lexical_rank.get(memory.id),
                vector_rank=vector_rank.get(memory.id),
                now=now or datetime.now(UTC),
            )
            for memory in combined.values()
        ]
        scored.sort(key=lambda item: (item.score, item.memory.importance), reverse=True)
        selected = scored[:top_k]
        self.store.mark_memories_accessed(item.memory.id for item in selected)
        trace = self.store.record_retrieval(
            session_id=session_id,
            query=query,
            candidate_count=len(combined),
            message_id=message_id,
            degraded_mode=degraded_mode,
            selected=[
                {
                    "memory_id": str(item.memory.id),
                    "canonical_key": item.memory.canonical_key,
                    "score": round(item.score, 6),
                    "factors": item.factors,
                }
                for item in selected
            ],
        )
        return RetrievalResult(memories=selected, trace=trace)

    def _score(
        self,
        memory: StoredMemory,
        *,
        query: str,
        lexical_rank: int | None,
        vector_rank: int | None,
        now: datetime,
    ) -> RetrievedMemory:
        raw_rrf = 0.0
        if lexical_rank is not None:
            raw_rrf += 1 / (self.rrf_k + lexical_rank)
        if vector_rank is not None:
            raw_rrf += 1 / (self.rrf_k + vector_rank)
        max_rrf = 2 / (self.rrf_k + 1)
        rrf = raw_rrf / max_rrf
        freshness = self._freshness(memory, now)
        entity = self._entity_overlap(query, memory)
        importance = memory.importance
        score = (0.65 * rrf) + (0.15 * importance) + (0.12 * freshness) + (0.08 * entity)
        return RetrievedMemory(
            memory=memory,
            score=score,
            factors={
                "rrf": round(rrf, 6),
                "importance": round(importance, 6),
                "freshness": round(freshness, 6),
                "entity": round(entity, 6),
                "lexical_rank": float(lexical_rank or 0),
                "vector_rank": float(vector_rank or 0),
            },
        )

    @staticmethod
    def _freshness(memory: StoredMemory, now: datetime) -> float:
        reference = memory.valid_from or memory.updated_at
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=UTC)
        age_days = max(0.0, (now - reference).total_seconds() / 86_400)
        half_life = {
            MemoryType.PROFILE: 3_650.0,
            MemoryType.PREFERENCE: 180.0,
            MemoryType.STATE: 30.0,
            MemoryType.EVENT: 365.0,
            MemoryType.PLAN: 60.0,
        }[memory.memory_type]
        if memory.memory_type == MemoryType.PLAN and memory.valid_to is not None:
            due = memory.valid_to
            if due.tzinfo is None:
                due = due.replace(tzinfo=UTC)
            if now > due:
                age_days = (now - due).total_seconds() / 86_400
                half_life = 7.0
        return math.pow(0.5, age_days / half_life)

    @staticmethod
    def _entity_overlap(query: str, memory: StoredMemory) -> float:
        query_tokens = set(re.findall(r"\w+", query.casefold(), flags=re.UNICODE))
        memory_tokens = set(
            re.findall(
                r"\w+",
                f"{memory.subject} {memory.predicate} {memory.value}".casefold(),
                flags=re.UNICODE,
            )
        )
        if not query_tokens:
            return 0.0
        return len(query_tokens & memory_tokens) / len(query_tokens)
