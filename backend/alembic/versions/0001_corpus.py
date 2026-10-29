"""corpus: documents, provisions, chunks, corpus_state

Revision ID: 0001
Revises:
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("so_hieu", sa.String(64), nullable=False, unique=True),
        sa.Column("doc_type", sa.String(32), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("issuer", sa.String(128)),
        sa.Column("passed_date", sa.Date()),
        sa.Column("effective_date", sa.Date()),
        sa.Column("expiry_date", sa.Date()),
        sa.Column("aliases", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("preamble", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("source_file", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "provisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("level", sa.String(8), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("dieu", sa.String(16), nullable=False),
        sa.Column("khoan", sa.Integer()),
        sa.Column("diem", sa.String(4)),
        sa.Column("title", sa.Text()),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("chapter_number", sa.String(16)),
        sa.Column("chapter_title", sa.Text()),
        sa.Column("section_number", sa.String(16)),
        sa.Column("section_title", sa.Text()),
        sa.Column("valid_from", sa.Date()),
        sa.Column("valid_to", sa.Date()),
        sa.UniqueConstraint("document_id", "path"),
        sa.CheckConstraint("level IN ('dieu', 'khoan', 'diem')", name="provisions_level"),
    )
    op.create_index("ix_provisions_document_id", "provisions", ["document_id"])

    op.create_table(
        "chunks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("article_number", sa.String(16), nullable=False),
        sa.Column("article_title", sa.Text(), nullable=False),
        sa.Column("chapter_number", sa.String(16)),
        sa.Column("chapter_title", sa.Text()),
        sa.Column("section_number", sa.String(16)),
        sa.Column("section_title", sa.Text()),
        sa.Column("clauses", postgresql.ARRAY(sa.Integer()), nullable=False),
        sa.Column("points", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("context_text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.Date()),
        sa.Column("valid_to", sa.Date()),
        sa.UniqueConstraint("document_id", "path"),
    )
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])
    op.create_index("ix_chunks_document_article", "chunks", ["document_id", "article_number"])

    corpus_state = op.create_table(
        "corpus_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("id = 1", name="corpus_state_single_row"),
    )
    op.bulk_insert(corpus_state, [{"id": 1, "version": 0}])


def downgrade() -> None:
    op.drop_table("corpus_state")
    op.drop_table("chunks")
    op.drop_table("provisions")
    op.drop_table("documents")
