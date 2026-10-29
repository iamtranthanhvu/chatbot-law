import hashlib
import math
from pathlib import Path

import pytest
from qdrant_client import AsyncQdrantClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lawqa.db.models import ChunkRow, CorpusState, Document
from lawqa.ingestion.indexer import QdrantIndexer
from lawqa.ingestion.service import IngestService
from lawqa.ingestion.tokens import HFTokenCounter
from lawqa.retrieval.encoder_client import EncoderUnavailableError

pytestmark = [pytest.mark.integration, pytest.mark.corpus]

RAW_FILE = Path(__file__).resolve().parents[3] / "raw_data" / "Luật-45-2013-QH13.docx"
COLLECTION = "test_chunks"
DIMENSION = 8


class FakeEncoder:
    """Deterministic unit vectors derived from the text hash."""

    def __init__(self) -> None:
        self.calls = 0

    async def embed_dense(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            raw = [b - 127.5 for b in digest[:DIMENSION]]
            norm = math.sqrt(sum(v * v for v in raw))
            vectors.append([v / norm for v in raw])
        return vectors


class DownEncoder:
    async def embed_dense(self, texts: list[str]) -> list[list[float]]:
        raise EncoderUnavailableError("Không kết nối được model-server tại http://127.0.0.1:8001")


@pytest.fixture(scope="module")
def counter() -> HFTokenCounter:
    return HFTokenCounter("BAAI/bge-m3")


def _service(
    session_factory: async_sessionmaker[AsyncSession],
    qdrant: AsyncQdrantClient,
    counter: HFTokenCounter,
    encoder: object,
) -> IngestService:
    return IngestService(
        session_factory=session_factory,
        encoder=encoder,  # type: ignore[arg-type]
        indexer=QdrantIndexer(qdrant, COLLECTION, dimension=DIMENSION),
        counter=counter,
        max_tokens=512,
    )


async def _postgres_chunk_ids(session_factory: async_sessionmaker[AsyncSession]) -> set[str]:
    async with session_factory() as session:
        return {str(i) for i in (await session.scalars(select(ChunkRow.id))).all()}


async def _qdrant_ids(qdrant: AsyncQdrantClient) -> set[str]:
    points, _ = await qdrant.scroll(COLLECTION, limit=10_000, with_payload=False)
    return {str(point.id) for point in points}


async def test_ingest_writes_postgres_and_qdrant_with_the_same_ids(
    session_factory: async_sessionmaker[AsyncSession],
    qdrant: AsyncQdrantClient,
    counter: HFTokenCounter,
) -> None:
    report = await _service(session_factory, qdrant, counter, FakeEncoder()).ingest(RAW_FILE)

    assert report.store.status == "created"
    assert report.indexed == report.store.chunks
    postgres_ids = await _postgres_chunk_ids(session_factory)
    assert len(postgres_ids) == report.store.chunks
    assert await _qdrant_ids(qdrant) == postgres_ids

    points, _ = await qdrant.scroll(COLLECTION, limit=1, with_payload=True)
    payload = points[0].payload or {}
    assert payload["so_hieu"] == "45/2013/QH13"
    assert payload["valid_from"] == "2014-07-01T00:00:00Z"
    assert "valid_to" not in payload
    assert payload["text"] and payload["context_text"].startswith("Luật Đất đai (45/2013/QH13)")


async def test_ingesting_the_same_file_again_skips_embedding(
    session_factory: async_sessionmaker[AsyncSession],
    qdrant: AsyncQdrantClient,
    counter: HFTokenCounter,
) -> None:
    encoder = FakeEncoder()
    service = _service(session_factory, qdrant, counter, encoder)
    await service.ingest(RAW_FILE)

    report = await service.ingest(RAW_FILE)

    assert report.store.status == "unchanged"
    assert encoder.calls == 1
    async with session_factory() as session:
        assert await session.scalar(select(CorpusState.version)) == 1


async def test_reindex_rebuilds_the_same_points_from_postgres(
    session_factory: async_sessionmaker[AsyncSession],
    qdrant: AsyncQdrantClient,
    counter: HFTokenCounter,
) -> None:
    service = _service(session_factory, qdrant, counter, FakeEncoder())
    await service.ingest(RAW_FILE)
    before = await _qdrant_ids(qdrant)
    await qdrant.delete_collection(COLLECTION)

    count = await service.reindex()

    assert count == len(before)
    assert await _qdrant_ids(qdrant) == before


async def test_remove_deletes_the_document_everywhere(
    session_factory: async_sessionmaker[AsyncSession],
    qdrant: AsyncQdrantClient,
    counter: HFTokenCounter,
) -> None:
    service = _service(session_factory, qdrant, counter, FakeEncoder())
    await service.ingest(RAW_FILE)

    assert await service.remove("45/2013/QH13") is True
    assert await service.remove("45/2013/QH13") is False

    assert await _qdrant_ids(qdrant) == set()
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Document)) == 0
        assert await session.scalar(select(CorpusState.version)) == 2


async def test_model_server_down_leaves_postgres_untouched(
    session_factory: async_sessionmaker[AsyncSession],
    qdrant: AsyncQdrantClient,
    counter: HFTokenCounter,
) -> None:
    with pytest.raises(EncoderUnavailableError, match="model-server"):
        await _service(session_factory, qdrant, counter, DownEncoder()).ingest(RAW_FILE)

    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Document)) == 0
        assert await session.scalar(select(CorpusState.version)) == 0
