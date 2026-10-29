import asyncio
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lawqa.db.migrate import downgrade, upgrade
from lawqa.db.models import ChunkRow, CorpusState, Document, Provision
from lawqa.db.session import create_engine
from lawqa.ingestion.chunker import Chunk, chunk_document
from lawqa.ingestion.legal_parser import parse_body, parse_file
from lawqa.ingestion.metadata import DocumentMetadata
from lawqa.ingestion.models import ParsedDocument
from lawqa.ingestion.store import DocumentExistsError, save_document
from lawqa.ingestion.tokens import HFTokenCounter

pytestmark = pytest.mark.integration

RAW_FILE = Path(__file__).resolve().parents[3] / "raw_data" / "Luật-45-2013-QH13.docx"


@pytest.fixture(scope="module")
def law_2013() -> tuple[ParsedDocument, list[Chunk]]:
    document = parse_file(RAW_FILE)
    return document, chunk_document(document, HFTokenCounter("BAAI/bge-m3"), 512)


async def _count(session: AsyncSession, model: type, **filters: object) -> int:
    query = select(func.count()).select_from(model).filter_by(**filters)
    return int(await session.scalar(query) or 0)


async def _version(session: AsyncSession) -> int:
    return int(await session.scalar(select(CorpusState.version)) or 0)


def test_upgrade_and_downgrade(postgres_url: str) -> None:
    async def table_names() -> set[str]:
        engine = create_engine(postgres_url)
        async with engine.connect() as connection:
            names = await connection.run_sync(lambda sync: set(inspect(sync).get_table_names()))
        await engine.dispose()
        return names

    downgrade(postgres_url, "base")
    assert {"documents", "provisions", "chunks"}.isdisjoint(asyncio.run(table_names()))

    upgrade(postgres_url)
    assert {"documents", "provisions", "chunks", "corpus_state"} <= asyncio.run(table_names())


@pytest.mark.corpus
async def test_saves_the_2013_law(
    session_factory: async_sessionmaker[AsyncSession],
    law_2013: tuple[ParsedDocument, list[Chunk]],
) -> None:
    document, chunks = law_2013

    result = await save_document(session_factory, document, chunks)

    assert result.status == "created"
    assert result.corpus_version == 1
    async with session_factory() as session:
        assert await _count(session, Document) == 1
        assert await _count(session, Provision, level="dieu") == 212
        assert await _count(session, Provision, level="khoan") == 782
        assert await _count(session, Provision, level="diem") == 609
        assert await _count(session, ChunkRow) == len(chunks)
        article_100 = await session.scalar(select(Provision).filter_by(path="dieu-100"))
        assert article_100 is not None
        assert article_100.text.startswith("Điều 100. Cấp Giấy chứng nhận")
        assert article_100.valid_from == date(2014, 7, 1)
        point = await session.scalar(select(Provision).filter_by(path="dieu-100/khoan-1/diem-đ"))
        assert point is not None and point.text.startswith("đ) Giấy tờ thanh lý")
        stored = await session.scalar(select(Document))
        assert stored is not None and "Luật Đất đai 2013" in stored.aliases


@pytest.mark.corpus
async def test_saving_the_same_file_again_changes_nothing(
    session_factory: async_sessionmaker[AsyncSession],
    law_2013: tuple[ParsedDocument, list[Chunk]],
) -> None:
    document, chunks = law_2013
    await save_document(session_factory, document, chunks)

    result = await save_document(session_factory, document, chunks)

    assert result.status == "unchanged"
    assert result.corpus_version == 1
    async with session_factory() as session:
        assert await _version(session) == 1
        assert await _count(session, ChunkRow) == len(chunks)


@pytest.mark.corpus
async def test_a_different_file_for_the_same_document_needs_replace(
    session_factory: async_sessionmaker[AsyncSession],
    law_2013: tuple[ParsedDocument, list[Chunk]],
) -> None:
    document, chunks = law_2013
    await save_document(session_factory, document, chunks)
    edited = document.model_copy(update={"sha256": "0" * 64})

    with pytest.raises(DocumentExistsError, match="45/2013/QH13"):
        await save_document(session_factory, edited, chunks)

    result = await save_document(session_factory, edited, chunks, replace=True)

    assert result.status == "replaced"
    assert result.corpus_version == 2
    async with session_factory() as session:
        assert await _count(session, Document) == 1
        assert await _count(session, Provision, level="dieu") == 212
        assert await session.scalar(select(Document.sha256)) == "0" * 64


async def test_a_failure_part_way_rolls_back_everything(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    document = ParsedDocument(
        metadata=DocumentMetadata(
            so_hieu="1/2020/QH14",
            doc_type="Luật",
            title="Thử",
            name="Luật Thử",
            issuer=None,
            passed_date=None,
            effective_date=None,
        ),
        preamble=[],
        structure=parse_body(["Điều 1. Thử", "Nội dung."]),
        sha256="a" * 64,
        source_file="thu.docx",
    )
    chunk = Chunk(
        path="dieu-1",
        order=0,
        article_number="1",
        article_title="Thử",
        chapter_number=None,
        chapter_title=None,
        section_number=None,
        section_title=None,
        clauses=[],
        points=[],
        text="Nội dung.",
        context_text="Luật Thử > Điều 1. Thử\nNội dung.",
        token_count=10,
    )

    with pytest.raises(Exception):  # noqa: B017 - duplicate chunk path violates a unique key
        await save_document(session_factory, document, [chunk, chunk])

    async with session_factory() as session:
        assert await _count(session, Document) == 0
        assert await _count(session, Provision) == 0
        assert await _version(session) == 0
        assert (await session.execute(text("SELECT 1"))).scalar() == 1
