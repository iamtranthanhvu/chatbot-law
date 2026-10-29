import logging
from datetime import date
from typing import Literal

from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient, models

from lawqa.ingestion.indexer import DENSE, SPARSE
from lawqa.retrieval.bm25 import encode_query
from lawqa.retrieval.encoder_client import DenseEncoder
from lawqa.retrieval.filters import valid_at
from lawqa.retrieval.types import RetrievedChunk, Stage

RetrievalMode = Literal["dense", "bm25", "hybrid"]

logger = logging.getLogger("lawqa.retrieval")


class RetrievalSettings(BaseModel):
    collection: str
    mode: RetrievalMode = "hybrid"
    dense_top_k: int = 50
    sparse_top_k: int = 50
    fused_top_k: int = 40


class HybridRetriever:
    def __init__(
        self, qdrant: AsyncQdrantClient, encoder: DenseEncoder, settings: RetrievalSettings
    ) -> None:
        self._qdrant = qdrant
        self._encoder = encoder
        self._settings = settings

    async def search(
        self, texts: list[str], reference_date: date, *, mode: RetrievalMode | None = None
    ) -> list[RetrievedChunk]:
        """Search every query text with the chosen signals and fuse all rankings with RRF."""
        s = self._settings
        mode = mode or s.mode
        query_filter = valid_at(reference_date)
        prefetch: list[models.Prefetch] = []

        if mode in ("dense", "hybrid"):
            for vector in await self._encoder.embed_dense(texts):
                prefetch.append(
                    models.Prefetch(
                        query=vector, using=DENSE, filter=query_filter, limit=s.dense_top_k
                    )
                )
        if mode in ("bm25", "hybrid"):
            for text in texts:
                sparse = encode_query(text)
                if not sparse.indices:
                    continue
                prefetch.append(
                    models.Prefetch(
                        query=models.SparseVector(indices=sparse.indices, values=sparse.values),
                        using=SPARSE,
                        filter=query_filter,
                        limit=s.sparse_top_k,
                    )
                )

        stage: Stage
        if not prefetch:
            points: list[models.ScoredPoint] = []
            stage = "fused"
        elif len(prefetch) == 1:
            only = prefetch[0]
            stage = "dense" if only.using == DENSE else "bm25"
            response = await self._qdrant.query_points(
                s.collection,
                query=only.query,
                using=only.using,
                query_filter=query_filter,
                limit=s.fused_top_k,
                with_payload=True,
            )
            points = response.points
        else:
            stage = "fused"
            response = await self._qdrant.query_points(
                s.collection,
                prefetch=prefetch,
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                query_filter=query_filter,
                limit=s.fused_top_k,
                with_payload=True,
            )
            points = response.points

        results = [RetrievedChunk.from_point(point, stage) for point in points]
        logger.info(
            "retrieval.search",
            extra={
                "mode": mode,
                "queries": len(texts),
                "dense_top_k": s.dense_top_k,
                "sparse_top_k": s.sparse_top_k,
                "fused_top_k": s.fused_top_k,
                "reference_date": reference_date.isoformat(),
                "results": len(results),
            },
        )
        return results
