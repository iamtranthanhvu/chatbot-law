import re
import uuid
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import delete, insert, select, update
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
