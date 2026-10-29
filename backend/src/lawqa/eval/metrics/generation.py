import math
import re
from collections.abc import Sequence
from difflib import SequenceMatcher

from lawqa.eval.dataset import Citation
from lawqa.eval.metrics.retrieval import RankedChunk, matches
from lawqa.pipelines.base import Source

REFUSAL_MARKERS = ("không tìm thấy căn cứ", "chỉ hỗ trợ", "ngoài phạm vi")
SITUATION_SECTIONS = ("kết luận", "căn cứ pháp lý")
# Shortest run of words copied from the article that counts as quoting it.
MIN_QUOTE_CHARS = 40
_MARKUP = re.compile(r"\[\d+\]|[\"“”*]")


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


def answer_structure(
    intent: str | None, answer: str, sources: Sequence[Source], gold: list[Citation]
) -> bool | None:
    """Whether an answer has the shape its intent's template asks for; None if no shape is set."""
    if intent == "situation":
        lowered = answer.lower()
        return all(section in lowered for section in SITUATION_SECTIONS)
    if intent == "lookup":
        asked = {g.dieu for g in gold}
        text = _plain(answer)
        return any(
            _longest_common_run(text, _plain(source.context)) >= MIN_QUOTE_CHARS
            for source in sources
            if source.dieu in asked
        )
    return None


def _plain(text: str) -> str:
    return " ".join(_MARKUP.sub(" ", text).lower().split())


def _longest_common_run(a: str, b: str) -> int:
    return SequenceMatcher(None, a, b, autojunk=False).find_longest_match().size


def percentile(values: Sequence[float], p: float) -> float:
    """Linear-interpolated percentile (same convention as numpy's default)."""
    ordered = sorted(values)
    position = (len(ordered) - 1) * p / 100
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _as_chunk(source: Source) -> RankedChunk:
    return RankedChunk(so_hieu=source.so_hieu, article_number=source.dieu, clauses=source.khoan)
