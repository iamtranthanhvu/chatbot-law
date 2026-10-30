import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lawqa.api.deps import get_session_factory
from lawqa.core.errors import NotFoundError
from lawqa.ingestion.store import ChunkWithDocument, get_chunk, list_documents

router = APIRouter(tags=["corpus"])

SessionFactory = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]


class DocumentOut(BaseModel):
    so_hieu: str
    name: str
    effective_date: date | None
    expiry_date: date | None
    chunks: int


class ChunkOut(BaseModel):
    id: uuid.UUID
    so_hieu: str
    document_name: str
    path: str
    chapter_number: str | None
    chapter_title: str | None
    section_number: str | None
    section_title: str | None
    dieu: str
    article_title: str
    khoan: list[int]
    diem: list[str]
    location: str
    text: str
    valid_from: date | None
    valid_to: date | None

    @classmethod
    def from_chunk(cls, chunk: ChunkWithDocument) -> "ChunkOut":
        return cls(
            id=chunk.id,
            so_hieu=chunk.so_hieu,
            document_name=chunk.document_name,
            path=chunk.path,
            chapter_number=chunk.chapter_number,
            chapter_title=chunk.chapter_title,
            section_number=chunk.section_number,
            section_title=chunk.section_title,
            dieu=chunk.article_number,
            article_title=chunk.article_title,
            khoan=chunk.clauses,
            diem=chunk.points,
            location=_location(chunk),
            text=chunk.text,
            valid_from=chunk.valid_from,
            valid_to=chunk.valid_to,
        )


@router.get("/documents")
async def documents(session_factory: SessionFactory) -> list[DocumentOut]:
    return [
        DocumentOut.model_validate(summary, from_attributes=True)
        for summary in await list_documents(session_factory)
    ]


@router.get("/chunks/{chunk_id}")
async def chunk(chunk_id: uuid.UUID, session_factory: SessionFactory) -> ChunkOut:
    found = await get_chunk(session_factory, chunk_id)
    if found is None:
        raise NotFoundError("Không tìm thấy đoạn văn bản.")
    return ChunkOut.from_chunk(found)


def _location(chunk: ChunkWithDocument) -> str:
    parts = []
    if chunk.chapter_number:
        parts.append(_titled(f"Chương {chunk.chapter_number}", chunk.chapter_title))
    if chunk.section_number:
        parts.append(_titled(f"Mục {chunk.section_number}", chunk.section_title))
    parts.append(_titled(f"Điều {chunk.article_number}", chunk.article_title))
    return " › ".join(parts)


def _titled(label: str, title: str | None) -> str:
    return f"{label}. {title}" if title else label
