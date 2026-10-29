import math
from collections.abc import Sequence

from lawqa.eval.dataset import Citation
from lawqa.eval.metrics.retrieval import RankedChunk, matches
from lawqa.pipelines.base import Source

REFUSAL_MARKERS = ("không tìm thấy căn cứ", "chỉ hỗ trợ", "ngoài phạm vi")


def is_refusal(answer: str) -> bool:
    lowered = answer.lower()
    return any(marker in lowered for marker in REFUSAL_MARKERS)


def citation_scores(
    cited: list[int], sources: Sequence[Source], gold: list[Citation]
) -> dict[str, float]:
    """Precision: share of cited sources that are a gold article/clause.
    Recall: share of gold citations covered by the cited sources."""
    cited_sources = [_as_chunk(source) for source in sources if source.n in cited]
    relevant = [chunk for chunk in cited_sources if any(matches(chunk, g) for g in gold)]
    covered = [g for g in gold if any(matches(chunk, g) for chunk in cited_sources)]
    return {
        "citation_precision": len(relevant) / len(cited_sources) if cited_sources else 0.0,
        "citation_recall": len(covered) / len(gold) if gold else 0.0,
    }


def percentile(values: Sequence[float], p: float) -> float:
    """Linear-interpolated percentile (same convention as numpy's default)."""
    ordered = sorted(values)
    position = (len(ordered) - 1) * p / 100
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _as_chunk(source: Source) -> RankedChunk:
    return RankedChunk(so_hieu=source.so_hieu, article_number=source.dieu, clauses=source.khoan)
