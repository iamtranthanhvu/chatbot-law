from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lawqa.ingestion.chunker import chunk_document
from lawqa.ingestion.legal_parser import parse_file
from lawqa.ingestion.store import save_document
from lawqa.ingestion.tokens import HFTokenCounter
from lawqa.retrieval.citation_lookup import CitationAwareRetriever, CitationLookup
from lawqa.retrieval.types import RetrievedChunk
from lawqa.understanding.citation_regex import extract_citations

pytestmark = [pytest.mark.integration, pytest.mark.corpus]

RAW_FILE = Path(__file__).resolve().parents[3] / "raw_data" / "Luật-45-2013-QH13.docx"


@pytest.fixture
async def lookup(session_factory: async_sessionmaker[AsyncSession]) -> CitationLookup:
    document = parse_file(RAW_FILE)
    chunks = chunk_document(document, HFTokenCounter("BAAI/bge-m3"), 512)
    await save_document(session_factory, document, chunks)
    return CitationLookup(session_factory)


async def _find(lookup: CitationLookup, question: str) -> list[tuple[str, list[int]]]:
    chunks = await lookup.find(extract_citations(question))
    assert {c.stage for c in chunks} <= {"lookup"}
    return [(c.path, c.clauses) for c in chunks]


async def test_whole_article(lookup: CitationLookup) -> None:
    found = await _find(lookup, "Điều 100 Luật Đất đai quy định gì?")

    assert found and all(path.startswith("dieu-100") for path, _ in found)
    assert sorted({n for _, clauses in found for n in clauses}) == [1, 2, 3, 4, 5]


async def test_clause_only_returns_chunks_holding_that_clause(lookup: CitationLookup) -> None:
    found = await _find(lookup, "Khoản 1 Điều 126 quy định gì?")

    assert found and all(1 in clauses for _, clauses in found)


async def test_point_reference_returns_the_clause_holding_the_point(lookup: CitationLookup) -> None:
    chunks = await lookup.find(extract_citations("điểm đ khoản 1 Điều 100"))

    assert chunks and "1.đ" in chunks[0].points
    assert "đ) Giấy tờ thanh lý" in chunks[0].text


async def test_unknown_article_or_document_finds_nothing(lookup: CitationLookup) -> None:
    assert await _find(lookup, "Điều 999 quy định gì?") == []
    assert await _find(lookup, "Điều 5 Luật số 31/2024/QH15") == []


class _NoResults:
    async def search(
        self, texts: list[str], reference_date: date, *, mode: str | None = None
    ) -> list[RetrievedChunk]:
        return []


async def test_every_article_named_in_a_question_is_the_first_source(
    lookup: CitationLookup,
) -> None:
    retriever = CitationAwareRetriever(_NoResults(), lookup)
    wrong = []
    for number in range(1, 213):
        found = await retriever.search([f"Điều {number} quy định gì?"], date(2026, 10, 29))
        if not found or found[0].article_number != str(number):
            wrong.append(number)

    assert wrong == []
