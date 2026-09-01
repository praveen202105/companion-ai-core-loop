from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from math import sqrt
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, text

from companion.domain import (
    MemoryAction,
    MemoryCandidate,
    MemoryEventView,
    MemoryStatus,
    MessageRole,
    MessageView,
    RetrievalTraceView,
    StoredMemory,
    utc_now,
)
from companion.storage.database import Database
from companion.storage.models import (
    MemoryEventRecord,
    MemoryRecord,
    MessageRecord,
    RetrievalTraceRecord,
    SessionRecord,
)


def canonical_slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    return normalized.strip("_")


def canonical_key(candidate: MemoryCandidate) -> str:
    parts = [
        candidate.owner.value,
        canonical_slug(candidate.subject),
        canonical_slug(candidate.predicate),
    ]
    if candidate.memory_type.value == "event":
        parts.extend(
            (
                candidate.valid_from.date().isoformat()
                if candidate.valid_from is not None
                else "undated",
                canonical_slug(candidate.value),
            )
        )
    return ":".join(parts)


class SqlAlchemyMemoryStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_session(self, *, persona_version: str, retention_days: int = 30) -> UUID:
        now = utc_now()
        record = SessionRecord(
            persona_version=persona_version,
            created_at=now,
            last_activity_at=now,
            expires_at=now + timedelta(days=retention_days),
        )
        with self.database.session_factory.begin() as session:
            session.add(record)
        return UUID(record.id)

    def session_exists(self, session_id: UUID) -> bool:
        with self.database.session_factory() as session:
            return session.get(SessionRecord, str(session_id)) is not None

    def append_message(
        self,
        *,
        session_id: UUID,
        role: MessageRole,
        content: str,
        request_id: str | None = None,
        model: str | None = None,
        prompt_version: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> MessageView:
        with self.database.session_factory.begin() as session:
            current = session.scalar(
                select(func.max(MessageRecord.sequence_no)).where(
                    MessageRecord.session_id == str(session_id)
                )
            )
            record = MessageRecord(
                session_id=str(session_id),
                sequence_no=(current or 0) + 1,
                role=role.value,
                content=content,
                request_id=request_id,
                model=model,
                prompt_version=prompt_version,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            session.add(record)
            parent = session.get(SessionRecord, str(session_id))
            if parent is None:
                raise LookupError(f"Session {session_id} does not exist")
            parent.last_activity_at = utc_now()
            session.flush()
            return self._message_view(record)

    def list_messages(self, session_id: UUID, *, limit: int | None = None) -> list[MessageView]:
        statement = (
            select(MessageRecord)
            .where(MessageRecord.session_id == str(session_id))
            .order_by(MessageRecord.sequence_no.asc())
        )
        if limit is not None:
            statement = statement.limit(limit)
        with self.database.session_factory() as session:
            return [self._message_view(row) for row in session.scalars(statement).all()]

    def get_message_by_request(self, session_id: UUID, request_id: str) -> MessageView | None:
        with self.database.session_factory() as session:
            record = session.scalar(
                select(MessageRecord).where(
                    MessageRecord.session_id == str(session_id),
                    MessageRecord.request_id == request_id,
                )
            )
            return self._message_view(record) if record else None

    def add_memory(
        self,
        *,
        session_id: UUID,
        candidate: MemoryCandidate,
        source_message_id: UUID | None = None,
        embedding: list[float] | None = None,
    ) -> StoredMemory:
        record = MemoryRecord(
            session_id=str(session_id),
            owner=candidate.owner.value,
            memory_type=candidate.memory_type.value,
            subject=candidate.subject,
            predicate=candidate.predicate,
            value=candidate.value,
            canonical_key=canonical_key(candidate),
            normalized_text=candidate.normalized_text,
            status=MemoryStatus.ACTIVE.value,
            confidence=candidate.confidence,
            importance=candidate.importance,
            valid_from=candidate.valid_from,
            valid_to=candidate.valid_to,
            expires_at=candidate.expires_at,
            source_message_id=str(source_message_id) if source_message_id else None,
            embedding=embedding,
        )
        with self.database.session_factory.begin() as session:
            session.add(record)
            session.flush()
            self._add_event(
                session=session,
                session_id=session_id,
                memory_id=UUID(record.id),
                source_message_id=source_message_id,
                action=MemoryAction.ADD,
                key=record.canonical_key,
                previous=None,
                candidate=candidate.model_dump(mode="json"),
                reason_code="new_canonical_fact",
            )
            return self._memory_view(record)

    def active_memory(self, session_id: UUID, key: str) -> StoredMemory | None:
        with self.database.session_factory() as session:
            record = session.scalar(
                select(MemoryRecord).where(
                    MemoryRecord.session_id == str(session_id),
                    MemoryRecord.canonical_key == key,
                    MemoryRecord.status == MemoryStatus.ACTIVE.value,
                )
            )
            return self._memory_view(record) if record else None

    def list_memories(
        self,
        session_id: UUID,
        *,
        status: MemoryStatus | None = None,
    ) -> list[StoredMemory]:
        statement = select(MemoryRecord).where(MemoryRecord.session_id == str(session_id))
        if status is not None:
            statement = statement.where(MemoryRecord.status == status.value)
        statement = statement.order_by(MemoryRecord.created_at.asc())
        with self.database.session_factory() as session:
            return [self._memory_view(row) for row in session.scalars(statement).all()]

    def search_lexical(
        self,
        *,
        session_id: UUID,
        query: str,
        limit: int = 20,
    ) -> list[StoredMemory]:
        if self.database.engine.dialect.name != "sqlite":
            raise NotImplementedError(
                "PostgreSQL lexical search is provided by PostgresMemoryStore"
            )
        tokens = re.findall(r"\w+", query.casefold(), flags=re.UNICODE)
        if not tokens:
            return []
        fts_query = " OR ".join(f'"{token.replace(chr(34), "")}"' for token in tokens)
        sql = text(
            """SELECT memory_id FROM memory_fts
            WHERE memory_fts MATCH :query AND session_id = :session_id
            ORDER BY bm25(memory_fts)
            LIMIT :limit"""
        )
        with self.database.session_factory() as session:
            ids = list(
                session.scalars(
                    sql,
                    {"query": fts_query, "session_id": str(session_id), "limit": limit},
                )
            )
            return self._ordered_memories(session, ids)

    def search_vector(
        self,
        *,
        session_id: UUID,
        query_embedding: list[float],
        limit: int = 20,
    ) -> list[StoredMemory]:
        with self.database.session_factory() as session:
            records = list(
                session.scalars(
                    select(MemoryRecord).where(
                        MemoryRecord.session_id == str(session_id),
                        MemoryRecord.status == MemoryStatus.ACTIVE.value,
                        MemoryRecord.embedding.is_not(None),
                    )
                )
            )
            records.sort(
                key=lambda record: self._cosine_similarity(
                    query_embedding, record.embedding or []
                ),
                reverse=True,
            )
            return [self._memory_view(record) for record in records[:limit]]

    def mark_memories_accessed(self, memory_ids: Iterable[UUID]) -> None:
        ids = [str(memory_id) for memory_id in memory_ids]
        if not ids:
            return
        with self.database.session_factory.begin() as session:
            records = list(
                session.scalars(select(MemoryRecord).where(MemoryRecord.id.in_(ids)))
            )
            now = utc_now()
            for record in records:
                record.access_count += 1
                record.last_accessed_at = now

    def update_memory(
        self,
        *,
        memory_id: UUID,
        candidate: MemoryCandidate,
        source_message_id: UUID | None,
        reason_code: str,
        embedding: list[float] | None = None,
    ) -> StoredMemory:
        with self.database.session_factory.begin() as session:
            record = session.get(MemoryRecord, str(memory_id))
            if record is None:
                raise LookupError(f"Memory {memory_id} does not exist")
            previous = self._snapshot(record)
            record.value = candidate.value
            record.normalized_text = candidate.normalized_text
            record.confidence = candidate.confidence
            record.importance = candidate.importance
            record.valid_from = candidate.valid_from
            record.valid_to = candidate.valid_to
            record.expires_at = candidate.expires_at
            record.source_message_id = str(source_message_id) if source_message_id else None
            record.embedding = embedding
            record.updated_at = utc_now()
            self._add_event(
                session=session,
                session_id=UUID(record.session_id),
                memory_id=memory_id,
                source_message_id=source_message_id,
                action=MemoryAction.UPDATE,
                key=record.canonical_key,
                previous=previous,
                candidate=candidate.model_dump(mode="json"),
                reason_code=reason_code,
            )
            session.flush()
            return self._memory_view(record)

    def supersede_memory(
        self,
        *,
        old_memory_id: UUID,
        candidate: MemoryCandidate,
        source_message_id: UUID | None,
        embedding: list[float] | None = None,
        reason_code: str = "changed_current_truth",
    ) -> StoredMemory:
        with self.database.session_factory.begin() as session:
            old = session.get(MemoryRecord, str(old_memory_id))
            if old is None:
                raise LookupError(f"Memory {old_memory_id} does not exist")
            if old.status != MemoryStatus.ACTIVE.value:
                raise ValueError("Only an active memory can be superseded")
            previous = self._snapshot(old)
            old.status = MemoryStatus.SUPERSEDED.value
            old.valid_to = candidate.valid_from or utc_now()
            old.updated_at = utc_now()
            new = MemoryRecord(
                session_id=old.session_id,
                owner=candidate.owner.value,
                memory_type=candidate.memory_type.value,
                subject=candidate.subject,
                predicate=candidate.predicate,
                value=candidate.value,
                canonical_key=old.canonical_key,
                normalized_text=candidate.normalized_text,
                status=MemoryStatus.ACTIVE.value,
                confidence=candidate.confidence,
                importance=candidate.importance,
                valid_from=candidate.valid_from or utc_now(),
                valid_to=candidate.valid_to,
                expires_at=candidate.expires_at,
                source_message_id=str(source_message_id) if source_message_id else None,
                embedding=embedding,
            )
            session.add(new)
            session.flush()
            old.superseded_by_id = new.id
            self._add_event(
                session=session,
                session_id=UUID(old.session_id),
                memory_id=UUID(new.id),
                source_message_id=source_message_id,
                action=MemoryAction.SUPERSEDE,
                key=old.canonical_key,
                previous=previous,
                candidate=candidate.model_dump(mode="json"),
                reason_code=reason_code,
            )
            session.flush()
            return self._memory_view(new)

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
    ) -> MemoryEventView:
        with self.database.session_factory.begin() as session:
            record = self._add_event(
                session=session,
                session_id=session_id,
                memory_id=memory_id,
                source_message_id=source_message_id,
                action=action,
                key=key,
                previous=previous,
                candidate=candidate,
                reason_code=reason_code,
            )
            session.flush()
            return self._event_view(record)

    def memory_history(self, session_id: UUID, key: str | None = None) -> list[MemoryEventView]:
        statement = select(MemoryEventRecord).where(
            MemoryEventRecord.session_id == str(session_id)
        )
        if key is not None:
            statement = statement.where(MemoryEventRecord.canonical_key == key)
        statement = statement.order_by(MemoryEventRecord.created_at.asc())
        with self.database.session_factory() as session:
            return [self._event_view(row) for row in session.scalars(statement).all()]

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
    ) -> RetrievalTraceView:
        record = RetrievalTraceRecord(
            session_id=str(session_id),
            message_id=str(message_id) if message_id else None,
            query=query,
            algorithm_version=algorithm_version,
            candidate_count=candidate_count,
            selected=selected,
            degraded_mode=degraded_mode,
        )
        with self.database.session_factory.begin() as session:
            session.add(record)
            session.flush()
            return self._retrieval_view(record)

    def latest_retrieval(self, session_id: UUID) -> RetrievalTraceView | None:
        with self.database.session_factory() as session:
            record = session.scalar(
                select(RetrievalTraceRecord)
                .where(RetrievalTraceRecord.session_id == str(session_id))
                .order_by(RetrievalTraceRecord.created_at.desc())
                .limit(1)
            )
            return self._retrieval_view(record) if record else None

    def delete_session(self, session_id: UUID) -> bool:
        with self.database.session_factory.begin() as session:
            record = session.get(SessionRecord, str(session_id))
            if record is None:
                return False
            session.delete(record)
            return True

    def cleanup_expired_sessions(self, *, now: datetime | None = None) -> int:
        threshold = now or datetime.now(UTC)
        with self.database.session_factory.begin() as session:
            expired_count = session.scalar(
                select(func.count(SessionRecord.id)).where(
                    SessionRecord.expires_at <= threshold
                )
            )
            session.execute(delete(SessionRecord).where(SessionRecord.expires_at <= threshold))
            return int(expired_count or 0)

    def _ordered_memories(self, session: Any, ids: list[str]) -> list[StoredMemory]:
        if not ids:
            return []
        records = list(
            session.scalars(
                select(MemoryRecord).where(
                    MemoryRecord.id.in_(ids),
                    MemoryRecord.status == MemoryStatus.ACTIVE.value,
                )
            )
        )
        by_id = {record.id: record for record in records}
        return [self._memory_view(by_id[memory_id]) for memory_id in ids if memory_id in by_id]

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if len(left) != len(right) or not left:
            return -1.0
        dot = sum(a * b for a, b in zip(left, right, strict=True))
        left_norm = sqrt(sum(value * value for value in left))
        right_norm = sqrt(sum(value * value for value in right))
        if left_norm == 0 or right_norm == 0:
            return -1.0
        return dot / (left_norm * right_norm)

    @staticmethod
    def _message_view(record: MessageRecord) -> MessageView:
        return MessageView(
            id=UUID(record.id),
            session_id=UUID(record.session_id),
            sequence_no=record.sequence_no,
            role=MessageRole(record.role),
            content=record.content,
            request_id=record.request_id,
            model=record.model,
            prompt_version=record.prompt_version,
            input_tokens=record.input_tokens,
            output_tokens=record.output_tokens,
            created_at=record.created_at,
        )

    @staticmethod
    def _memory_view(record: MemoryRecord) -> StoredMemory:
        return StoredMemory(
            id=UUID(record.id),
            session_id=UUID(record.session_id),
            owner=record.typed_owner,
            memory_type=record.typed_memory_type,
            subject=record.subject,
            predicate=record.predicate,
            value=record.value,
            canonical_key=record.canonical_key,
            normalized_text=record.normalized_text,
            status=record.typed_status,
            confidence=record.confidence,
            importance=record.importance,
            valid_from=record.valid_from,
            valid_to=record.valid_to,
            expires_at=record.expires_at,
            source_message_id=UUID(record.source_message_id) if record.source_message_id else None,
            superseded_by_id=UUID(record.superseded_by_id) if record.superseded_by_id else None,
            embedding=record.embedding,
            access_count=record.access_count,
            created_at=record.created_at,
            updated_at=record.updated_at,
            last_accessed_at=record.last_accessed_at,
        )

    @staticmethod
    def _event_view(record: MemoryEventRecord) -> MemoryEventView:
        return MemoryEventView(
            id=UUID(record.id),
            session_id=UUID(record.session_id),
            memory_id=UUID(record.memory_id) if record.memory_id else None,
            source_message_id=UUID(record.source_message_id) if record.source_message_id else None,
            action=record.typed_action,
            canonical_key=record.canonical_key,
            previous_snapshot=record.previous_snapshot,
            candidate_snapshot=record.candidate_snapshot,
            reason_code=record.reason_code,
            created_at=record.created_at,
        )

    @staticmethod
    def _retrieval_view(record: RetrievalTraceRecord) -> RetrievalTraceView:
        return RetrievalTraceView(
            id=UUID(record.id),
            session_id=UUID(record.session_id),
            message_id=UUID(record.message_id) if record.message_id else None,
            query=record.query,
            algorithm_version=record.algorithm_version,
            candidate_count=record.candidate_count,
            selected=record.selected,
            degraded_mode=record.degraded_mode,
            created_at=record.created_at,
        )

    @staticmethod
    def _snapshot(record: MemoryRecord) -> dict[str, Any]:
        return {
            "id": record.id,
            "value": record.value,
            "status": record.status,
            "valid_from": record.valid_from.isoformat() if record.valid_from else None,
            "valid_to": record.valid_to.isoformat() if record.valid_to else None,
            "confidence": record.confidence,
            "importance": record.importance,
        }

    @staticmethod
    def _add_event(
        *,
        session: Any,
        session_id: UUID,
        memory_id: UUID | None,
        source_message_id: UUID | None,
        action: MemoryAction,
        key: str | None,
        previous: dict[str, Any] | None,
        candidate: dict[str, Any] | None,
        reason_code: str,
    ) -> MemoryEventRecord:
        record = MemoryEventRecord(
            session_id=str(session_id),
            memory_id=str(memory_id) if memory_id else None,
            source_message_id=str(source_message_id) if source_message_id else None,
            action=action.value,
            canonical_key=key,
            previous_snapshot=previous,
            candidate_snapshot=candidate,
            reason_code=reason_code,
        )
        session.add(record)
        return record
