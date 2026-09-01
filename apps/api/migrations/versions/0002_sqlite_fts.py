"""Add SQLite FTS5 support for active memory retrieval."""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_sqlite_fts"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        return
    op.execute(
        """CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
            memory_id UNINDEXED,
            session_id UNINDEXED,
            normalized_text,
            tokenize='unicode61 remove_diacritics 2'
        )"""
    )
    op.execute(
        """CREATE TRIGGER IF NOT EXISTS memory_fts_insert AFTER INSERT ON memories
        WHEN new.status = 'active' BEGIN
            INSERT INTO memory_fts(memory_id, session_id, normalized_text)
            VALUES (new.id, new.session_id, new.normalized_text);
        END"""
    )
    op.execute(
        """CREATE TRIGGER IF NOT EXISTS memory_fts_delete AFTER DELETE ON memories BEGIN
            DELETE FROM memory_fts WHERE memory_id = old.id;
        END"""
    )
    op.execute(
        """CREATE TRIGGER IF NOT EXISTS memory_fts_update AFTER UPDATE ON memories BEGIN
            DELETE FROM memory_fts WHERE memory_id = old.id;
            INSERT INTO memory_fts(memory_id, session_id, normalized_text)
            SELECT new.id, new.session_id, new.normalized_text
            WHERE new.status = 'active';
        END"""
    )
    op.execute(
        """INSERT INTO memory_fts(memory_id, session_id, normalized_text)
        SELECT id, session_id, normalized_text FROM memories WHERE status = 'active'"""
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        return
    op.execute("DROP TRIGGER IF EXISTS memory_fts_update")
    op.execute("DROP TRIGGER IF EXISTS memory_fts_delete")
    op.execute("DROP TRIGGER IF EXISTS memory_fts_insert")
    op.execute("DROP TABLE IF EXISTS memory_fts")
