"""Create the persistent companion memory schema."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("persona_version", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])

    op.create_table(
        "messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("request_id", sa.String(80)),
        sa.Column("model", sa.String(120)),
        sa.Column("prompt_version", sa.String(32)),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("session_id", "sequence_no", name="uq_message_session_sequence"),
        sa.UniqueConstraint("session_id", "request_id", name="uq_message_session_request"),
    )
    op.create_index("ix_messages_session_id", "messages", ["session_id"])

    op.create_table(
        "memories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("owner", sa.String(16), nullable=False),
        sa.Column("memory_type", sa.String(24), nullable=False),
        sa.Column("subject", sa.String(120), nullable=False),
        sa.Column("predicate", sa.String(120), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("canonical_key", sa.String(280), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("importance", sa.Float(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "source_message_id",
            sa.String(36),
            sa.ForeignKey("messages.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "superseded_by_id",
            sa.String(36),
            sa.ForeignKey("memories.id", ondelete="SET NULL"),
        ),
        sa.Column("embedding", sa.JSON()),
        sa.Column("access_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_memories_session_id", "memories", ["session_id"])
    op.create_index("ix_memory_session_status", "memories", ["session_id", "status"])
    op.create_index(
        "uq_active_memory_canonical_key",
        "memories",
        ["session_id", "canonical_key"],
        unique=True,
        sqlite_where=sa.text("status = 'active'"),
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "memory_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("memory_id", sa.String(36), sa.ForeignKey("memories.id", ondelete="SET NULL")),
        sa.Column(
            "source_message_id",
            sa.String(36),
            sa.ForeignKey("messages.id", ondelete="SET NULL"),
        ),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("canonical_key", sa.String(280)),
        sa.Column("previous_snapshot", sa.JSON()),
        sa.Column("candidate_snapshot", sa.JSON()),
        sa.Column("reason_code", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_memory_events_session_id", "memory_events", ["session_id"])
    op.create_index(
        "ix_memory_event_session_created", "memory_events", ["session_id", "created_at"]
    )

    op.create_table(
        "retrieval_traces",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("message_id", sa.String(36), sa.ForeignKey("messages.id", ondelete="SET NULL")),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("algorithm_version", sa.String(32), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("selected", sa.JSON(), nullable=False),
        sa.Column("degraded_mode", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_retrieval_traces_session_id", "retrieval_traces", ["session_id"])
    op.create_index(
        "ix_retrieval_session_created", "retrieval_traces", ["session_id", "created_at"]
    )

    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("suite_name", sa.String(120), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("metrics", sa.JSON()),
        sa.Column("failures", sa.JSON()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("evaluation_runs")
    op.drop_table("retrieval_traces")
    op.drop_table("memory_events")
    op.drop_table("memories")
    op.drop_table("messages")
    op.drop_table("sessions")
