from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql.type_api import TypeEngine
from sqlalchemy.types import TypeDecorator

from companion.domain import (
    MemoryAction,
    MemoryOwner,
    MemoryStatus,
    MemoryType,
    MessageRole,
    utc_now,
)


def new_uuid() -> str:
    return str(uuid4())


class EmbeddingVector(TypeDecorator[list[float]]):
    """SQLite JSON locally and pgvector's native vector type in PostgreSQL."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector

            return dialect.type_descriptor(Vector(384))
        return dialect.type_descriptor(JSON())


class Base(DeclarativeBase):
    pass


class UserRecord(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint(
            "auth_provider",
            "auth_subject",
            name="uq_user_auth_provider_subject",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    auth_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    auth_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SessionRecord(Base):
    __tablename__ = "sessions"
    __table_args__ = (UniqueConstraint("user_id", name="uq_sessions_user_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    persona_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class MessageRecord(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence_no", name="uq_message_session_sequence"),
        UniqueConstraint("session_id", "request_id", name="uq_message_session_request"),
        UniqueConstraint(
            "session_id",
            "reply_to_request_id",
            name="uq_message_session_reply_request",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reply_to_request_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    @property
    def typed_role(self) -> MessageRole:
        return MessageRole(self.role)


class MemoryRecord(Base):
    __tablename__ = "memories"
    __table_args__ = (
        Index(
            "uq_active_memory_canonical_key",
            "session_id",
            "canonical_key",
            unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_memory_session_status", "session_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    owner: Mapped[str] = mapped_column(String(16), nullable=False)
    memory_type: Mapped[str] = mapped_column(String(24), nullable=False)
    subject: Mapped[str] = mapped_column(String(120), nullable=False)
    predicate: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_key: Mapped[str] = mapped_column(String(280), nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=MemoryStatus.ACTIVE)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    importance: Mapped[float] = mapped_column(Float, nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_message_id: Mapped[str | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    superseded_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("memories.id", ondelete="SET NULL"), nullable=True
    )
    embedding: Mapped[list[float] | None] = mapped_column(EmbeddingVector(), nullable=True)
    access_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def typed_owner(self) -> MemoryOwner:
        return MemoryOwner(self.owner)

    @property
    def typed_memory_type(self) -> MemoryType:
        return MemoryType(self.memory_type)

    @property
    def typed_status(self) -> MemoryStatus:
        return MemoryStatus(self.status)


class MemoryEventRecord(Base):
    __tablename__ = "memory_events"
    __table_args__ = (Index("ix_memory_event_session_created", "session_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    memory_id: Mapped[str | None] = mapped_column(
        ForeignKey("memories.id", ondelete="SET NULL"), nullable=True
    )
    source_message_id: Mapped[str | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    canonical_key: Mapped[str | None] = mapped_column(String(280), nullable=True)
    previous_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    candidate_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    reason_code: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    @property
    def typed_action(self) -> MemoryAction:
        return MemoryAction(self.action)


class RetrievalTraceRecord(Base):
    __tablename__ = "retrieval_traces"
    __table_args__ = (Index("ix_retrieval_session_created", "session_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[str | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(32), nullable=False)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    selected: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    degraded_mode: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EvaluationRunRecord(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    suite_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    failures: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
