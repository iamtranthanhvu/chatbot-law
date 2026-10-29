import re
from collections.abc import Iterable

from pydantic import BaseModel

from lawqa.ingestion.chunker import TokenCounter
from lawqa.retrieval.types import RetrievedChunk


class ContextSource(BaseModel):
    """One numbered source given to the LLM: the retrieved parts of a single article."""

    n: int
    so_hieu: str
    document_name: str
    article_number: str
    article_title: str
    chunks: list[RetrievedChunk]
    text: str

    @property
    def score(self) -> float:
        return max(chunk.score for chunk in self.chunks)


def pack_context(
    chunks: list[RetrievedChunk], counter: TokenCounter, max_tokens: int
) -> list[ContextSource]:
    """Keep the most relevant chunks that fit the budget, grouped by article in reading order."""
    selected: list[RetrievedChunk] = []
    seen: set[str] = set()
    for chunk in sorted(chunks, key=lambda c: c.score, reverse=True):
        if chunk.chunk_id in seen:
            continue
        candidate = [*selected, chunk]
        if _token_total(candidate, counter) <= max_tokens:
            selected = candidate
            seen.add(chunk.chunk_id)
    return _number(_groups(selected))


def _token_total(chunks: list[RetrievedChunk], counter: TokenCounter) -> int:
    return sum(counter.count(source.text) for source in _number(_groups(chunks)))


def _groups(chunks: Iterable[RetrievedChunk]) -> list[list[RetrievedChunk]]:
    by_article: dict[tuple[str, str], list[RetrievedChunk]] = {}
    for chunk in chunks:
        by_article.setdefault((chunk.so_hieu, chunk.article_number), []).append(chunk)
    ordered = sorted(by_article.items(), key=lambda item: (item[0][0], _article_key(item[0][1])))
    return [sorted(group, key=lambda c: c.ordinal) for _, group in ordered]


def _number(groups: list[list[RetrievedChunk]]) -> list[ContextSource]:
    sources = []
    for n, group in enumerate(groups, start=1):
        first = group[0]
        name = _document_name(first)
        header = (
            f"[{n}] {name} ({first.so_hieu}) — Điều {first.article_number}. {first.article_title}"
        )
        sources.append(
            ContextSource(
                n=n,
                so_hieu=first.so_hieu,
                document_name=name,
                article_number=first.article_number,
                article_title=first.article_title,
                chunks=group,
                text="\n".join([header, _body(group)]),
            )
        )
    return sources


def _body(group: list[RetrievedChunk]) -> str:
    parts: list[str] = []
    for previous, chunk in zip([None, *group], group, strict=False):
        if previous is not None and chunk.ordinal != previous.ordinal + 1:
            parts.append("…")
        parts.append(chunk.text)
    return "\n".join(parts)


def _article_key(number: str) -> tuple[int, str]:
    match = re.match(r"(\d+)(.*)", number)
    return (int(match.group(1)), match.group(2)) if match else (0, number)


def _document_name(chunk: RetrievedChunk) -> str:
    # context_text starts with the breadcrumb "{document name} ({so_hieu}) > ...".
    head = chunk.context_text.split(f" ({chunk.so_hieu})", 1)[0]
    return head if head and "\n" not in head else "Văn bản"
