import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    so_hieu: Mapped[str] = mapped_column(String(64), unique=True)
    doc_type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    issuer: Mapped[str | None] = mapped_column(String(128))
    passed_date: Mapped[date | None] = mapped_column(Date)
    effective_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(Text))
    preamble: Mapped[list[str]] = mapped_column(ARRAY(Text))
    source_file: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Provision(Base):
    __tablename__ = "provisions"
    __table_args__ = (
        UniqueConstraint("document_id", "path"),
        CheckConstraint("level IN ('dieu', 'khoan', 'diem')", name="provisions_level"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    path: Mapped[str] = mapped_column(Text)
    level: Mapped[str] = mapped_column(String(8))
    position: Mapped[int] = mapped_column(Integer)
    dieu: Mapped[str] = mapped_column(String(16))
    khoan: Mapped[int | None] = mapped_column(Integer)
    diem: Mapped[str | None] = mapped_column(String(4))
    title: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    chapter_number: Mapped[str | None] = mapped_column(String(16))
    chapter_title: Mapped[str | None] = mapped_column(Text)
    section_number: Mapped[str | None] = mapped_column(String(16))
    section_title: Mapped[str | None] = mapped_column(Text)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)


class ChunkRow(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "path"),
        Index("ix_chunks_document_article", "document_id", "article_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    path: Mapped[str] = mapped_column(Text)
    ordinal: Mapped[int] = mapped_column(Integer)
    article_number: Mapped[str] = mapped_column(String(16))
    article_title: Mapped[str] = mapped_column(Text)
    chapter_number: Mapped[str | None] = mapped_column(String(16))
    chapter_title: Mapped[str | None] = mapped_column(Text)
    section_number: Mapped[str | None] = mapped_column(String(16))
    section_title: Mapped[str | None] = mapped_column(Text)
    clauses: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    points: Mapped[list[str]] = mapped_column(ARRAY(Text))
    text: Mapped[str] = mapped_column(Text)
    context_text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)


class CorpusState(Base):
    """Single row; version increases on every corpus change and keys answer caches."""

    __tablename__ = "corpus_state"
    __table_args__ = (CheckConstraint("id = 1", name="corpus_state_single_row"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class QueryLog(Base):
    __tablename__ = "queries"
    __table_args__ = (
        CheckConstraint("outcome IN ('done', 'error', 'cancelled')", name="queries_outcome"),
        Index("ix_queries_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    question: Mapped[str] = mapped_column(Text)
    intent: Mapped[str | None] = mapped_column(String(32))
    legal_query: Mapped[str | None] = mapped_column(Text)
    pipeline: Mapped[str] = mapped_column(String(32))
    config_hash: Mapped[str] = mapped_column(String(16))
    corpus_version: Mapped[int] = mapped_column(Integer)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    retrieved: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    answer: Mapped[str] = mapped_column(Text)
    citations: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    invalid_citations: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    missing_facts: Mapped[list[str]] = mapped_column(ARRAY(Text))
    latency_ms: Mapped[dict[str, int]] = mapped_column(JSONB)
    usage: Mapped[dict[str, int]] = mapped_column(JSONB)
    model: Mapped[str | None] = mapped_column(String(128))
    git_sha: Mapped[str] = mapped_column(String(32))
    cached: Mapped[bool] = mapped_column(Boolean)
    outcome: Mapped[str] = mapped_column(String(16))
    error_code: Mapped[str | None] = mapped_column(String(32))
    ip_hash: Mapped[str] = mapped_column(String(64))


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (CheckConstraint("rating IN ('up', 'down')", name="feedback_rating"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    query_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("queries.id", ondelete="CASCADE"), unique=True
    )
    rating: Mapped[str] = mapped_column(String(8))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
