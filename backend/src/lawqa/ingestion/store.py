import re
import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lawqa.db.models import ChunkRow, CorpusState, Document, Provision
from lawqa.ingestion.chunker import Chunk
from lawqa.ingestion.models import Article, ParsedDocument

LAWQA_NAMESPACE = uuid.UUID("6f1c2b52-8f0e-4d6b-9a57-3f4f2a8c9d10")


class DocumentExistsError(Exception):
    pass


class StoreResult(BaseModel):
    status: Literal["created", "unchanged", "replaced"]
    document_id: uuid.UUID
    corpus_version: int
    provisions: int
    chunks: int


def document_uuid(so_hieu: str) -> uuid.UUID:
    return uuid.uuid5(LAWQA_NAMESPACE, so_hieu)


def chunk_uuid(document_id: uuid.UUID, path: str) -> uuid.UUID:
    """Also the Qdrant point id, so re-indexing the same chunk overwrites it."""
    return uuid.uuid5(document_id, f"chunk:{path}")


def provision_uuid(document_id: uuid.UUID, path: str) -> uuid.UUID:
    return uuid.uuid5(document_id, f"provision:{path}")


async def save_document(
    session_factory: async_sessionmaker[AsyncSession],
    document: ParsedDocument,
    chunks: list[Chunk],
    *,
    replace: bool = False,
) -> StoreResult:
    """Write a document, its provisions and chunks in one transaction."""
    meta = document.metadata
    document_id = document_uuid(meta.so_hieu)
    provision_rows = build_provision_rows(document, document_id)
    chunk_rows = build_chunk_rows(document, document_id, chunks)

    def result(status: Literal["created", "unchanged", "replaced"], version: int) -> StoreResult:
        return StoreResult(
            status=status,
            document_id=document_id,
            corpus_version=version,
            provisions=len(provision_rows),
            chunks=len(chunk_rows),
        )

    async with session_factory() as session, session.begin():
        # Locking the single corpus_state row serializes concurrent ingests.
        version = await session.scalar(select(CorpusState.version).with_for_update())
        existing = (
            await session.execute(
                select(Document.id, Document.sha256).where(Document.so_hieu == meta.so_hieu)
            )
        ).first()

        status: Literal["created", "replaced"] = "created"
        if existing is not None:
            if existing.sha256 == document.sha256:
                return result("unchanged", int(version or 0))
            if not replace:
                raise DocumentExistsError(
                    f"Văn bản {meta.so_hieu} đã có trong hệ thống với nội dung khác; "
                    "dùng --replace để thay thế."
                )
            await session.execute(delete(Document).where(Document.id == existing.id))
            status = "replaced"

        await session.execute(insert(Document).values(**_document_values(document, document_id)))
        if provision_rows:
            await session.execute(insert(Provision), provision_rows)
        if chunk_rows:
            await session.execute(insert(ChunkRow), chunk_rows)
        new_version = await session.scalar(
            update(CorpusState)
            .values(version=CorpusState.version + 1)
            .returning(CorpusState.version)
        )
    return result(status, int(new_version or 0))


def _document_values(document: ParsedDocument, document_id: uuid.UUID) -> dict[str, Any]:
    meta = document.metadata
    return {
        "id": document_id,
        "so_hieu": meta.so_hieu,
        "doc_type": meta.doc_type,
        "title": meta.title,
        "name": meta.name,
        "issuer": meta.issuer,
        "passed_date": meta.passed_date,
        "effective_date": meta.effective_date,
        "expiry_date": None,
        "aliases": _aliases(document),
        "preamble": document.preamble,
        "source_file": document.source_file,
        "sha256": document.sha256,
    }


def _aliases(document: ParsedDocument) -> list[str]:
    meta = document.metadata
    aliases = [meta.name]
    if year := re.search(r"/(\d{4})/", meta.so_hieu):
        aliases.append(f"{meta.name} {year.group(1)}")
    return aliases


def build_provision_rows(document: ParsedDocument, document_id: uuid.UUID) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    effective = document.metadata.effective_date

    def add(article: Article, path: str, level: str, text: str, **extra: Any) -> None:
        rows.append(
            {
                "id": provision_uuid(document_id, path),
                "document_id": document_id,
                "path": path,
                "level": level,
                "position": len(rows),
                "dieu": article.number,
                "khoan": extra.get("khoan"),
                "diem": extra.get("diem"),
                "title": extra.get("title"),
                "text": text,
                "chapter_number": article.chapter_number,
                "chapter_title": article.chapter_title,
                "section_number": article.section_number,
                "section_title": article.section_title,
                "valid_from": effective,
                "valid_to": None,
            }
        )

    for article in document.structure.articles:
        base = article.path
        add(article, base, "dieu", "\n".join(article.all_lines()), title=article.title)
        for point in article.points:
            path = f"{base}/{point.path_segment}"
            add(article, path, "diem", "\n".join(point.lines), diem=point.letter)
        for clause in article.clauses:
            clause_path = f"{base}/{clause.path_segment}"
            add(article, clause_path, "khoan", "\n".join(clause.all_lines()), khoan=clause.number)
            for point in clause.points:
                path = f"{clause_path}/{point.path_segment}"
                text = "\n".join(point.lines)
                add(article, path, "diem", text, khoan=clause.number, diem=point.letter)
    return rows


def build_chunk_rows(
    document: ParsedDocument, document_id: uuid.UUID, chunks: list[Chunk]
) -> list[dict[str, Any]]:
    effective = document.metadata.effective_date
    return [
        {
            "id": chunk_uuid(document_id, chunk.path),
            "document_id": document_id,
            "path": chunk.path,
            "ordinal": chunk.order,
            "article_number": chunk.article_number,
            "article_title": chunk.article_title,
            "chapter_number": chunk.chapter_number,
            "chapter_title": chunk.chapter_title,
            "section_number": chunk.section_number,
            "section_title": chunk.section_title,
            "clauses": chunk.clauses,
            "points": chunk.points,
            "text": chunk.text,
            "context_text": chunk.context_text,
            "token_count": chunk.token_count,
            "valid_from": effective,
            "valid_to": None,
        }
        for chunk in chunks
    ]


class DocumentState(BaseModel):
    document_id: uuid.UUID
    sha256: str


class StoredChunk(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    so_hieu: str
    path: str
    ordinal: int
    article_number: str
    article_title: str
    chapter_number: str | None
    chapter_title: str | None
    section_number: str | None
    section_title: str | None
    clauses: list[int]
    points: list[str]
    text: str
    context_text: str
    token_count: int
    valid_from: date | None
    valid_to: date | None


class ChunkWithDocument(StoredChunk):
    document_name: str


class DocumentSummary(BaseModel):
    so_hieu: str
    name: str
    effective_date: date | None
    expiry_date: date | None
    source_file: str
    sha256: str
    chunks: int
    created_at: datetime


async def document_state(
    session_factory: async_sessionmaker[AsyncSession], so_hieu: str
) -> DocumentState | None:
    async with session_factory() as session:
        row = (
            await session.execute(
                select(Document.id, Document.sha256).where(Document.so_hieu == so_hieu)
            )
        ).first()
    return DocumentState(document_id=row.id, sha256=row.sha256) if row else None


async def load_chunks(
    session_factory: async_sessionmaker[AsyncSession], document_id: uuid.UUID | None = None
) -> list[StoredChunk]:
    query = (
        select(ChunkRow, Document.so_hieu)
        .join(Document, Document.id == ChunkRow.document_id)
        .order_by(
            Document.so_hieu,
            func.length(ChunkRow.article_number),
            ChunkRow.article_number,
            ChunkRow.ordinal,
        )
    )
    if document_id is not None:
        query = query.where(ChunkRow.document_id == document_id)
    async with session_factory() as session:
        rows = (await session.execute(query)).all()
    return [
        StoredChunk.model_validate({**_columns(chunk), "so_hieu": so_hieu})
        for chunk, so_hieu in rows
    ]


def _columns(row: ChunkRow) -> dict[str, Any]:
    return {column.key: getattr(row, column.key) for column in ChunkRow.__table__.columns}


async def remove_document(
    session_factory: async_sessionmaker[AsyncSession], so_hieu: str
) -> uuid.UUID | None:
    async with session_factory() as session, session.begin():
        await session.scalar(select(CorpusState.version).with_for_update())
        document_id = await session.scalar(
            delete(Document).where(Document.so_hieu == so_hieu).returning(Document.id)
        )
        if document_id is not None:
            await session.execute(update(CorpusState).values(version=CorpusState.version + 1))
    return document_id


async def list_documents(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[DocumentSummary]:
    query = (
        select(Document, func.count(ChunkRow.id))
        .outerjoin(ChunkRow, ChunkRow.document_id == Document.id)
        .group_by(Document.id)
        .order_by(Document.so_hieu)
    )
    async with session_factory() as session:
        rows = (await session.execute(query)).all()
    return [
        DocumentSummary(
            so_hieu=document.so_hieu,
            name=document.name,
            effective_date=document.effective_date,
            expiry_date=document.expiry_date,
            source_file=document.source_file,
            sha256=document.sha256,
            chunks=chunks,
            created_at=document.created_at,
        )
        for document, chunks in rows
    ]


async def find_article_chunks(
    session_factory: async_sessionmaker[AsyncSession], dieu: str, so_hieu: str | None = None
) -> list[StoredChunk]:
    query = (
        select(ChunkRow, Document.so_hieu)
        .join(Document, Document.id == ChunkRow.document_id)
        .where(ChunkRow.article_number == dieu)
        .order_by(Document.so_hieu, ChunkRow.ordinal)
    )
    if so_hieu is not None:
        query = query.where(Document.so_hieu == so_hieu)
    async with session_factory() as session:
        rows = (await session.execute(query)).all()
    return [
        StoredChunk.model_validate({**_columns(chunk), "so_hieu": doc_so_hieu})
        for chunk, doc_so_hieu in rows
    ]


async def get_chunk(
    session_factory: async_sessionmaker[AsyncSession], chunk_id: uuid.UUID
) -> ChunkWithDocument | None:
    query = (
        select(ChunkRow, Document.so_hieu, Document.name)
        .join(Document, Document.id == ChunkRow.document_id)
        .where(ChunkRow.id == chunk_id)
    )
    async with session_factory() as session:
        row = (await session.execute(query)).first()
    if row is None:
        return None
    chunk, so_hieu, name = row
    return ChunkWithDocument.model_validate(
        {**_columns(chunk), "so_hieu": so_hieu, "document_name": name}
    )
