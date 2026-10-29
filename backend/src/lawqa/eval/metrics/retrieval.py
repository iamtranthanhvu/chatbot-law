import math
from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel

from lawqa.eval.dataset import Citation

K_VALUES = (5, 10)


class ChunkLike(Protocol):
    @property
    def so_hieu(self) -> str: ...

    @property
    def article_number(self) -> str: ...

    @property
    def clauses(self) -> list[int]: ...


class RankedChunk(BaseModel):
    so_hieu: str
    article_number: str
    clauses: list[int]


def matches(chunk: ChunkLike, citation: Citation) -> bool:
    """A chunk is relevant when it is the cited article and, if a clause is cited, contains it.

    A chunk without clause numbers holds the whole (clause-less) article.
    """
    if chunk.so_hieu != citation.so_hieu or chunk.article_number != citation.dieu:
        return False
    return citation.khoan is None or not chunk.clauses or citation.khoan in chunk.clauses


def retrieval_metrics(ranked: Sequence[ChunkLike], gold: list[Citation]) -> dict[str, float] | None:
    """Recall@k, MRR@10 and nDCG@10 over the gold citations (None if there is no gold).

    Each gold citation earns credit once, at the first chunk that matches it.
    """
    if not gold:
        return None
    first_hit: dict[int, int] = {}
    for rank, chunk in enumerate(ranked, start=1):
        for index, citation in enumerate(gold):
            if index not in first_hit and matches(chunk, citation):
                first_hit[index] = rank

    metrics = {
        f"recall@{k}": sum(1 for r in first_hit.values() if r <= k) / len(gold) for k in K_VALUES
    }
    best = min(first_hit.values(), default=None)
    metrics["mrr@10"] = 1 / best if best is not None and best <= 10 else 0.0
    dcg = sum(1 / math.log2(rank + 1) for rank in first_hit.values() if rank <= 10)
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(len(gold), 10) + 1))
    metrics["ndcg@10"] = dcg / ideal
    return metrics
