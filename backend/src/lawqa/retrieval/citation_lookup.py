from datetime import date
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lawqa.ingestion.store import StoredChunk, find_article_chunks
from lawqa.retrieval.types import RetrievedChunk
from lawqa.understanding.citation_regex import CitationRef, extract_citations

LOOKUP_SCORE = 1.0


class CitationLookup:
    """Fetches the chunks of articles/clauses/points a question names explicitly."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def find(self, refs: list[CitationRef]) -> list[RetrievedChunk]:
        found: list[RetrievedChunk] = []
        seen: set[str] = set()
        for ref in refs:
            chunks = await find_article_chunks(self._session_factory, ref.dieu, ref.so_hieu)
            for chunk in _narrow(chunks, ref):
                if str(chunk.id) not in seen:
                    seen.add(str(chunk.id))
                    found.append(_retrieved(chunk))
        return found


def _narrow(chunks: list[StoredChunk], ref: CitationRef) -> list[StoredChunk]:
    if ref.khoan is None:
        return chunks
    # A chunk without clause numbers is a clause-less article and holds everything.
    in_clause = [c for c in chunks if not c.clauses or ref.khoan in c.clauses]
    if ref.diem is None:
        return in_clause
    point = f"{ref.khoan}.{ref.diem}"
    return [c for c in in_clause if point in c.points] or in_clause


def _retrieved(chunk: StoredChunk) -> RetrievedChunk:
    return RetrievedChunk.model_validate(
        {
            **chunk.model_dump(exclude={"id", "document_id"}),
            "chunk_id": str(chunk.id),
            "document_id": str(chunk.document_id),
            "score": LOOKUP_SCORE,
            "stage": "lookup",
        }
    )


class ModeRetriever(Protocol):
    async def search(
        self, texts: list[str], reference_date: date, *, mode: str | None = None
    ) -> list[RetrievedChunk]: ...


class Lookup(Protocol):
    async def find(self, refs: list[CitationRef]) -> list[RetrievedChunk]: ...


class CitationAwareRetriever:
    """Puts the articles a question names explicitly ("Điều 100", "khoản 1 Điều 126") first.

    Looked-up chunks bypass the validity filter on purpose: asking for an article by number
    must return it even if it is no longer in force.
    """

    def __init__(self, inner: ModeRetriever, lookup: Lookup, *, enabled: bool = True) -> None:
        self._inner = inner
        self._lookup = lookup
        self._enabled = enabled

    async def search(
        self, texts: list[str], reference_date: date, *, mode: str | None = None
    ) -> list[RetrievedChunk]:
        named = await self._lookup.find(extract_citations(texts[0])) if self._enabled else []
        results = await self._inner.search(texts, reference_date, mode=mode)
        seen = {chunk.chunk_id for chunk in named}
        return named + [chunk for chunk in results if chunk.chunk_id not in seen]
