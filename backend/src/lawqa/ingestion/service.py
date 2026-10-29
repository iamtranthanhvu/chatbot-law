import uuid
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lawqa.ingestion.chunker import Chunk, TokenCounter, chunk_document
from lawqa.ingestion.indexer import QdrantIndexer
from lawqa.ingestion.legal_parser import parse_file
from lawqa.ingestion.models import ParsedDocument
from lawqa.ingestion.store import (
    StoredChunk,
    StoreResult,
    document_state,
    load_chunks,
    remove_document,
    save_document,
)
from lawqa.retrieval.bm25 import BM25Params, average_length
from lawqa.retrieval.encoder_client import DenseEncoder


class IndexingError(RuntimeError):
    pass


class IngestReport(BaseModel):
    document: ParsedDocument
    chunks: list[Chunk]
    store: StoreResult
    indexed: int
    avgdl: float | None


class IngestService:
    """Parse → chunk → embed → Postgres (one transaction) → Qdrant.

    Embeddings are computed before anything is written so an unavailable model-server
    never leaves a half-ingested document behind.
    """

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        encoder: DenseEncoder,
        indexer: QdrantIndexer,
        counter: TokenCounter,
        max_tokens: int,
    ) -> None:
        self.session_factory = session_factory
        self._encoder = encoder
        self._indexer = indexer
        self._counter = counter
        self._max_tokens = max_tokens

    async def ingest(self, path: Path, *, replace: bool = False) -> IngestReport:
        document = parse_file(path)
        chunks = chunk_document(document, self._counter, self._max_tokens)

        state = await document_state(self.session_factory, document.metadata.so_hieu)
        if (
            state is not None
            and state.sha256 == document.sha256
            and await self._indexer.count(state.document_id) == len(chunks)
        ):
            result = await save_document(self.session_factory, document, chunks)
            return IngestReport(
                document=document, chunks=chunks, store=result, indexed=0, avgdl=None
            )

        vectors = await self._encoder.embed_dense([chunk.context_text for chunk in chunks])
        result = await save_document(self.session_factory, document, chunks, replace=replace)
        vectors_by_path = dict(zip((chunk.path for chunk in chunks), vectors, strict=True))
        try:
            avgdl = await self._index_document(result.document_id, vectors_by_path)
        except Exception as error:
            raise IndexingError(
                f"Đã lưu {document.metadata.so_hieu} vào Postgres nhưng ghi Qdrant thất bại "
                f"({error}). Chạy `lawqa reindex` để đồng bộ lại."
            ) from error
        return IngestReport(
            document=document, chunks=chunks, store=result, indexed=len(chunks), avgdl=avgdl
        )

    async def reindex(self) -> int:
        chunks = await load_chunks(self.session_factory)
        vectors = await self._encoder.embed_dense([chunk.context_text for chunk in chunks])
        await self._indexer.recreate_collection()
        if chunks:
            await self._indexer.upsert(chunks, vectors, self._bm25_params(chunks))
        return len(chunks)

    async def remove(self, so_hieu: str) -> bool:
        document_id = await remove_document(self.session_factory, so_hieu)
        if document_id is None:
            return False
        await self._indexer.delete_document(document_id)
        remaining = await load_chunks(self.session_factory)
        if remaining:
            await self._indexer.update_sparse(remaining, self._bm25_params(remaining))
        return True

    async def _index_document(
        self, document_id: uuid.UUID, vectors: dict[str, list[float]]
    ) -> float:
        all_chunks = await load_chunks(self.session_factory)
        params = self._bm25_params(all_chunks)
        own = [chunk for chunk in all_chunks if chunk.document_id == document_id]
        others = [chunk for chunk in all_chunks if chunk.document_id != document_id]

        await self._indexer.ensure_collection()
        await self._indexer.delete_document(document_id)
        await self._indexer.upsert(own, [vectors[chunk.path] for chunk in own], params)
        if others:
            await self._indexer.update_sparse(others, params)
        return params.avgdl

    @staticmethod
    def _bm25_params(chunks: list[StoredChunk]) -> BM25Params:
        return BM25Params(avgdl=average_length([chunk.context_text for chunk in chunks]))
