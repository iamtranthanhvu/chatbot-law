import itertools
import logging
import uuid
from datetime import date

import pytest
from qdrant_client import AsyncQdrantClient

from lawqa.ingestion.indexer import QdrantIndexer
from lawqa.ingestion.store import StoredChunk
from lawqa.retrieval.bm25 import BM25Params
from lawqa.retrieval.hybrid import HybridRetriever, RetrievalSettings

pytestmark = pytest.mark.integration

COLLECTION = "retrieval_test"
DOCUMENT_ID = uuid.uuid4()

# Two-dimensional "embeddings" make the dense ranking fully controlled by the test.
VECTORS = {
    "thu hồi đất": [1.0, 0.0],
    "giao đất": [0.0, 1.0],
}


class TableEncoder:
    async def embed_dense(self, texts: list[str]) -> list[list[float]]:
        return [VECTORS.get(text, [0.7071, 0.7071]) for text in texts]


def _chunk(
    path: str,
    text: str,
    *,
    valid_from: date | None = date(2014, 7, 1),
    valid_to: date | None = None,
) -> StoredChunk:
    return StoredChunk(
        id=uuid.uuid5(DOCUMENT_ID, path),
        document_id=DOCUMENT_ID,
        so_hieu="45/2013/QH13",
        path=path,
        ordinal=0,
        article_number=path.removeprefix("dieu-"),
        article_title=text[:20],
        chapter_number=None,
        chapter_title=None,
        section_number=None,
        section_title=None,
        clauses=[],
        points=[],
        text=text,
        context_text=text,
        token_count=10,
        valid_from=valid_from,
        valid_to=valid_to,
    )


CHUNKS = {
    # dense favours "thu hồi đất" queries; the text itself never says so
    "dieu-61": (_chunk("dieu-61", "Nhà nước lấy lại đất vì mục đích quốc phòng"), [1.0, 0.0]),
    # BM25 favours exact wording; dense points the other way
    "dieu-62": (_chunk("dieu-62", "Thu hồi đất thu hồi đất để phát triển kinh tế"), [0.0, 1.0]),
    "dieu-55": (_chunk("dieu-55", "Giao đất có thu tiền sử dụng đất"), [0.0, 1.0]),
    "dieu-99": (
        _chunk("dieu-99", "Thu hồi đất theo quy định cũ", valid_to=date(2020, 1, 1)),
        [1.0, 0.0],
    ),
    "dieu-300": (
        _chunk("dieu-300", "Thu hồi đất theo quy định tương lai", valid_from=date(2099, 1, 1)),
        [1.0, 0.0],
    ),
}


@pytest.fixture
async def retriever(qdrant: AsyncQdrantClient) -> HybridRetriever:
    indexer = QdrantIndexer(qdrant, COLLECTION, dimension=2)
    await indexer.ensure_collection()
    chunks = [chunk for chunk, _ in CHUNKS.values()]
    await indexer.upsert(chunks, [vector for _, vector in CHUNKS.values()], BM25Params(avgdl=8))
    settings = RetrievalSettings(collection=COLLECTION, dense_top_k=10, sparse_top_k=10)
    return HybridRetriever(qdrant, TableEncoder(), settings)


async def _paths(retriever: HybridRetriever, mode: str, on: date = date(2026, 10, 29)) -> list[str]:
    results = await retriever.search(["thu hồi đất"], on, mode=mode)  # type: ignore[arg-type]
    return [chunk.path for chunk in results]


async def test_dense_mode_ranks_by_meaning(retriever: HybridRetriever) -> None:
    assert (await _paths(retriever, "dense"))[0] == "dieu-61"


async def test_bm25_mode_ranks_by_exact_words(retriever: HybridRetriever) -> None:
    paths = await _paths(retriever, "bm25")

    assert paths[0] == "dieu-62"
    assert paths.index("dieu-61") > paths.index("dieu-55")  # only shares the syllable "đất"
    assert paths[0] != (await _paths(retriever, "dense"))[0]


async def test_hybrid_mode_fuses_both_rankings(retriever: HybridRetriever) -> None:
    paths = await _paths(retriever, "hybrid")

    assert {"dieu-61", "dieu-62"} <= set(paths[:2])


async def test_only_provisions_in_force_on_the_reference_date_are_returned(
    retriever: HybridRetriever,
) -> None:
    today = set(await _paths(retriever, "hybrid"))
    assert "dieu-99" not in today
    assert "dieu-300" not in today

    in_2019 = set(await _paths(retriever, "hybrid", on=date(2019, 6, 1)))
    assert "dieu-99" in in_2019


async def test_results_carry_payload_and_scores(retriever: HybridRetriever) -> None:
    results = await retriever.search(["thu hồi đất"], date(2026, 10, 29), mode="hybrid")

    top = results[0]
    assert top.so_hieu == "45/2013/QH13"
    assert top.text
    assert top.stage == "fused"
    assert all(a.score >= b.score for a, b in itertools.pairwise(results))


async def test_search_parameters_are_logged(
    retriever: HybridRetriever, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="lawqa.retrieval"):
        await retriever.search(["thu hồi đất", "giao đất"], date(2026, 10, 29), mode="hybrid")

    record = next(r for r in caplog.records if r.name == "lawqa.retrieval")
    assert record.mode == "hybrid"  # type: ignore[attr-defined]
    assert record.queries == 2  # type: ignore[attr-defined]
    assert record.dense_top_k == 10  # type: ignore[attr-defined]
