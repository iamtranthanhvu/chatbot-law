import logging
from datetime import date
from typing import Protocol

from pydantic import BaseModel

from lawqa.retrieval.types import RetrievedChunk

logger = logging.getLogger("lawqa.retrieval")

RERANK_SUFFIX = "+rerank"


class RerankScorer(Protocol):
    async def rerank(self, query: str, passages: list[str]) -> list[float]: ...


class FirstStageRetriever(Protocol):
    async def search(
        self, texts: list[str], reference_date: date, *, mode: str | None = None
    ) -> list[RetrievedChunk]: ...


class RerankSettings(BaseModel):
    top_n: int = 8
    # First-stage candidates sent to the cross-encoder (cost grows linearly, ~1 s each on M1).
    candidates: int = 40


class Reranker:
    """Cross-encoder scoring of first-stage candidates; best score over the query texts wins."""

    def __init__(self, scorer: RerankScorer, settings: RerankSettings) -> None:
        self._scorer = scorer
        self._settings = settings

    async def rerank(self, texts: list[str], chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        chunks = chunks[: self._settings.candidates]
        if not chunks:
            return []
        passages = [chunk.context_text for chunk in chunks]
        best = [0.0] * len(chunks)
        for text in texts:
            scores = await self._scorer.rerank(text, passages)
            best = [max(old, new) for old, new in zip(best, scores, strict=True)]
        ranked = sorted(zip(chunks, best, strict=True), key=lambda pair: pair[1], reverse=True)
        return [
            chunk.model_copy(update={"score": score, "stage": "rerank"})
            for chunk, score in ranked[: self._settings.top_n]
        ]


class RerankingRetriever:
    """Adds an optional rerank stage to a first-stage retriever.

    Modes: "dense" | "bm25" | "hybrid" (no rerank) or any of them followed by "+rerank".
    """

    def __init__(
        self,
        retriever: FirstStageRetriever,
        reranker: Reranker,
        default_mode: str = "hybrid+rerank",
    ) -> None:
        self._retriever = retriever
        self._reranker = reranker
        self._default_mode = default_mode

    async def search(
        self, texts: list[str], reference_date: date, *, mode: str | None = None
    ) -> list[RetrievedChunk]:
        mode = mode or self._default_mode
        first_stage = mode.removesuffix(RERANK_SUFFIX)
        candidates = await self._retriever.search(texts, reference_date, mode=first_stage)
        if not mode.endswith(RERANK_SUFFIX):
            return candidates
        reranked = await self._reranker.rerank(texts, candidates)
        logger.info(
            "retrieval.rerank",
            extra={
                "candidates": len(candidates),
                "kept": len(reranked),
                "best_score": reranked[0].score if reranked else None,
            },
        )
        return reranked
