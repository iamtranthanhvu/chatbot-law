"""queries log and answer feedback

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "queries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(32)),
        sa.Column("legal_query", sa.Text()),
        sa.Column("pipeline", sa.String(32), nullable=False),
        sa.Column("config_hash", sa.String(16), nullable=False),
        sa.Column("corpus_version", sa.Integer(), nullable=False),
        sa.Column("sources", postgresql.JSONB(), nullable=False),
        sa.Column("retrieved", postgresql.JSONB(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("citations", postgresql.ARRAY(sa.Integer()), nullable=False),
        sa.Column("invalid_citations", postgresql.ARRAY(sa.Integer()), nullable=False),
        sa.Column("missing_facts", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("latency_ms", postgresql.JSONB(), nullable=False),
        sa.Column("usage", postgresql.JSONB(), nullable=False),
        sa.Column("model", sa.String(128)),
        sa.Column("git_sha", sa.String(32), nullable=False),
        sa.Column("cached", sa.Boolean(), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("error_code", sa.String(32)),
        sa.Column("ip_hash", sa.String(64), nullable=False),
        sa.CheckConstraint("outcome IN ('done', 'error', 'cancelled')", name="queries_outcome"),
    )
    op.create_index("ix_queries_created_at", "queries", ["created_at"])
    op.create_table(
        "feedback",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "query_id",
            sa.Uuid(),
            sa.ForeignKey("queries.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("rating", sa.String(8), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("rating IN ('up', 'down')", name="feedback_rating"),
    )


def downgrade() -> None:
    op.drop_table("feedback")
    op.drop_index("ix_queries_created_at", table_name="queries")
    op.drop_table("queries")
