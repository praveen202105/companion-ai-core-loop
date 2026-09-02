"""Add authenticated users and persistent user-owned sessions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_authenticated_users"
down_revision: str | None = "0003_postgres_vector_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("auth_provider", sa.String(32), nullable=False),
        sa.Column("auth_subject", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "auth_provider",
            "auth_subject",
            name="uq_user_auth_provider_subject",
        ),
    )
    with op.batch_alter_table("sessions") as batch:
        batch.add_column(sa.Column("user_id", sa.String(36), nullable=True))
        batch.alter_column(
            "expires_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=True,
        )
        batch.create_foreign_key(
            "fk_sessions_user_id_users",
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_unique_constraint("uq_sessions_user_id", ["user_id"])
        batch.create_index("ix_sessions_user_id", ["user_id"], unique=False)


def downgrade() -> None:
    sessions = sa.table(
        "sessions",
        sa.column("expires_at", sa.DateTime(timezone=True)),
    )
    op.execute(
        sessions.update()
        .where(sessions.c.expires_at.is_(None))
        .values(expires_at=sa.func.now())
    )
    with op.batch_alter_table("sessions") as batch:
        batch.drop_index("ix_sessions_user_id")
        batch.drop_constraint("uq_sessions_user_id", type_="unique")
        batch.drop_constraint("fk_sessions_user_id_users", type_="foreignkey")
        batch.alter_column(
            "expires_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )
        batch.drop_column("user_id")
    op.drop_table("users")
