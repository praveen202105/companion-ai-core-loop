"""Add response idempotency and PostgreSQL retrieval indexes."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_postgres_vector_idempotency"
down_revision: str | None = "0002_sqlite_fts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    with op.batch_alter_table("messages") as batch:
        batch.add_column(sa.Column("reply_to_request_id", sa.String(80), nullable=True))
        batch.create_unique_constraint(
            "uq_message_session_reply_request",
            ["session_id", "reply_to_request_id"],
        )
    if dialect != "postgresql":
        return

    installed = op.get_bind().execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
    ).scalar_one()
    if not installed:
        raise RuntimeError(
            "pgvector is not installed. Run CREATE EXTENSION IF NOT EXISTS vector once "
            "as the database owner, then redeploy."
        )
    from pgvector.sqlalchemy import Vector

    op.alter_column(
        "memories",
        "embedding",
        existing_type=sa.JSON(),
        type_=Vector(384),
        postgresql_using="embedding::text::vector(384)",
    )
    op.execute(
        """CREATE INDEX ix_memories_normalized_text_fts ON memories USING gin (
        to_tsvector('simple', normalized_text)
        )"""
    )
    op.execute(
        """CREATE INDEX ix_memories_embedding_hnsw ON memories USING hnsw (
        embedding vector_cosine_ops
        ) WHERE embedding IS NOT NULL"""
    )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_memories_embedding_hnsw")
        op.execute("DROP INDEX IF EXISTS ix_memories_normalized_text_fts")
        op.alter_column(
            "memories",
            "embedding",
            existing_type=sa.Text(),
            type_=sa.JSON(),
            postgresql_using="to_json(embedding::text)",
        )
    with op.batch_alter_table("messages") as batch:
        batch.drop_constraint("uq_message_session_reply_request", type_="unique")
        batch.drop_column("reply_to_request_id")
