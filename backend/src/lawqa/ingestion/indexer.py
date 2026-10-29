import uuid
from collections.abc import Sequence
from datetime import date
from typing import Any

from qdrant_client import AsyncQdrantClient, models

from lawqa.ingestion.store import StoredChunk
from lawqa.retrieval.bm25 import BM25Params, encode_document

DENSE = "dense"
SPARSE = "bm25"

_PAYLOAD_INDEXES = {
    "document_id": models.PayloadSchemaType.KEYWORD,
    "so_hieu": models.PayloadSchemaType.KEYWORD,
    "article_number": models.PayloadSchemaType.KEYWORD,
    "valid_from": models.PayloadSchemaType.DATETIME,
    "valid_to": models.PayloadSchemaType.DATETIME,
}


class QdrantIndexer:
    def __init__(
        self,
        client: AsyncQdrantClient,
        collection: str,
        *,
        dimension: int = 1024,
        batch_size: int = 128,
    ) -> None:
        self._client = client
        self._collection = collection
        self._dimension = dimension
        self._batch_size = batch_size

    async def ensure_collection(self) -> None:
        if await self._client.collection_exists(self._collection):
            return
        await self._client.create_collection(
            self._collection,
            vectors_config={
                DENSE: models.VectorParams(size=self._dimension, distance=models.Distance.COSINE)
            },
            sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )
        for field, schema in _PAYLOAD_INDEXES.items():
            await self._client.create_payload_index(self._collection, field, field_schema=schema)

    async def recreate_collection(self) -> None:
        if await self._client.collection_exists(self._collection):
            await self._client.delete_collection(self._collection)
        await self.ensure_collection()

    async def upsert(
        self, chunks: Sequence[StoredChunk], dense: Sequence[list[float]], params: BM25Params
    ) -> None:
        points = [
            models.PointStruct(
                id=str(chunk.id),
                vector={DENSE: vector, SPARSE: _sparse(chunk.context_text, params)},
                payload=_payload(chunk),
            )
            for chunk, vector in zip(chunks, dense, strict=True)
        ]
        for start in range(0, len(points), self._batch_size):
            batch = points[start : start + self._batch_size]
            await self._client.upsert(self._collection, points=batch, wait=True)

    async def update_sparse(self, chunks: Sequence[StoredChunk], params: BM25Params) -> None:
        """Re-weight BM25 vectors after the corpus average length changed."""
        updates = [
            models.PointVectors(
                id=str(chunk.id), vector={SPARSE: _sparse(chunk.context_text, params)}
            )
            for chunk in chunks
        ]
        for start in range(0, len(updates), self._batch_size):
            batch = updates[start : start + self._batch_size]
            await self._client.update_vectors(self._collection, points=batch, wait=True)

    async def delete_document(self, document_id: uuid.UUID) -> None:
        if not await self._client.collection_exists(self._collection):
            return
        await self._client.delete(
            self._collection,
            points_selector=models.FilterSelector(filter=_document_filter(document_id)),
            wait=True,
        )

    async def count(self, document_id: uuid.UUID | None = None) -> int:
        if not await self._client.collection_exists(self._collection):
            return 0
        query_filter = _document_filter(document_id) if document_id else None
        result = await self._client.count(self._collection, count_filter=query_filter, exact=True)
        return result.count


def _document_filter(document_id: uuid.UUID) -> models.Filter:
    condition = models.FieldCondition(
        key="document_id", match=models.MatchValue(value=str(document_id))
    )
    return models.Filter(must=[condition])


def _sparse(text: str, params: BM25Params) -> models.SparseVector:
    vector = encode_document(text, params)
    return models.SparseVector(indices=vector.indices, values=vector.values)


def _payload(chunk: StoredChunk) -> dict[str, Any]:
    payload = chunk.model_dump(mode="json", exclude={"id", "valid_from", "valid_to", "document_id"})
    payload["chunk_id"] = str(chunk.id)
    payload["document_id"] = str(chunk.document_id)
    if chunk.valid_from:
        payload["valid_from"] = _datetime(chunk.valid_from)
    if chunk.valid_to:
        payload["valid_to"] = _datetime(chunk.valid_to)
    return payload


def _datetime(value: date) -> str:
    return f"{value.isoformat()}T00:00:00Z"
