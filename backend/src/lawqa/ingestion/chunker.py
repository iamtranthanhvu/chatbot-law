from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel

from lawqa.ingestion.models import Article, ParsedDocument
from lawqa.ingestion.normalize import sentence_case


class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...


class Chunk(BaseModel):
    path: str
    order: int
    article_number: str
    article_title: str
    chapter_number: str | None
    chapter_title: str | None
    section_number: str | None
    section_title: str | None
    clauses: list[int]
    points: list[str]  # "<clause>.<letter>"; clause 0 = point directly under the article
    text: str
    context_text: str
    token_count: int


@dataclass
class _Unit:
    lines: list[str]
    clauses: list[int]
    points: list[str]
    children: list["_Unit"] = field(default_factory=list)
    continuation_line: str | None = None

    def merge(self, other: "_Unit") -> "_Unit":
        clauses = self.clauses + [c for c in other.clauses if c not in self.clauses]
        return _Unit(self.lines + other.lines, clauses, self.points + other.points)


def chunk_document(document: ParsedDocument, counter: TokenCounter, max_tokens: int) -> list[Chunk]:
    chunker = _ArticleChunker(document, counter, max_tokens)
    chunks: list[Chunk] = []
    for article in document.structure.articles:
        chunks.extend(chunker.chunk(article))
    return chunks


class _ArticleChunker:
    def __init__(self, document: ParsedDocument, counter: TokenCounter, max_tokens: int) -> None:
        self._document = document
        self._counter = counter
        self._max_tokens = max_tokens

    def chunk(self, article: Article) -> list[Chunk]:
        crumb = self._breadcrumb(article)
        whole = _article_unit(article)
        if self._fits(crumb, whole.lines):
            return [self._to_chunk(article, f"dieu-{article.number}", 0, whole, crumb)]

        pieces = self._pack(whole.children, crumb, crumb)
        return [
            self._to_chunk(article, f"dieu-{article.number}/p{i}", i - 1, unit, prefix)
            for i, (unit, prefix) in enumerate(pieces, start=1)
        ]

    def _pack(
        self, units: list[_Unit], first_prefix: str, rest_prefix: str
    ) -> list[tuple[_Unit, str]]:
        """Greedily merge consecutive units; recursively split units that never fit."""
        pieces: list[tuple[_Unit, str]] = []
        current: _Unit | None = None

        def prefix() -> str:
            return first_prefix if not pieces else rest_prefix

        for unit in units:
            if current is not None:
                merged = current.merge(unit)
                if self._fits(prefix(), merged.lines):
                    current = merged
                    continue
                pieces.append((current, prefix()))
                current = None
            if self._fits(prefix(), unit.lines):
                current = unit
                continue
            sub_rest = rest_prefix
            if unit.continuation_line:
                sub_rest = f"{rest_prefix}\n{unit.continuation_line}"
            pieces.extend(self._pack(self._split(unit, sub_rest), prefix(), sub_rest))
        if current is not None:
            pieces.append((current, prefix()))
        return pieces

    def _split(self, unit: _Unit, prefix: str) -> list[_Unit]:
        if unit.children:
            return unit.children
        if len(unit.lines) > 1:
            return [_Unit([line], unit.clauses, unit.points) for line in unit.lines]
        return [
            _Unit([piece], unit.clauses, unit.points)
            for piece in self._split_words(unit.lines[0], prefix)
        ]

    def _split_words(self, line: str, prefix: str) -> list[str]:
        budget = self._max_tokens - self._counter.count(prefix) - 2
        pieces: list[str] = []
        current: list[str] = []
        for word in line.split():
            candidate = " ".join([*current, word])
            if current and self._counter.count(candidate) > budget:
                pieces.append(" ".join(current))
                current = [word]
            else:
                current.append(word)
        if current:
            pieces.append(" ".join(current))
        return pieces

    def _fits(self, prefix: str, lines: list[str]) -> bool:
        return self._counter.count(_context(prefix, lines)) <= self._max_tokens

    def _breadcrumb(self, article: Article) -> str:
        meta = self._document.metadata
        parts = [f"{meta.name} ({meta.so_hieu})"]
        if article.chapter_number:
            parts.append(
                f"Chương {article.chapter_number}. {sentence_case(article.chapter_title or '')}"
            )
        if article.section_number:
            parts.append(
                f"Mục {article.section_number}. {sentence_case(article.section_title or '')}"
            )
        parts.append(article.heading)
        return " > ".join(parts)

    def _to_chunk(self, article: Article, path: str, order: int, unit: _Unit, prefix: str) -> Chunk:
        context = _context(prefix, unit.lines)
        return Chunk(
            path=path,
            order=order,
            article_number=article.number,
            article_title=article.title,
            chapter_number=article.chapter_number,
            chapter_title=article.chapter_title,
            section_number=article.section_number,
            section_title=article.section_title,
            clauses=unit.clauses,
            points=unit.points,
            text="\n".join(unit.lines),
            context_text=context,
            token_count=self._counter.count(context),
        )


def _article_unit(article: Article) -> _Unit:
    children: list[_Unit] = []
    lead_lines = [*article.intro, *(line for p in article.points for line in p.lines)]
    if lead_lines:
        children.append(
            _Unit(
                lead_lines,
                [],
                [f"0.{p.letter}" for p in article.points],
                children=[
                    *([_Unit(article.intro, [], [])] if article.intro else []),
                    *(_Unit(p.lines, [], [f"0.{p.letter}"]) for p in article.points),
                ],
            )
        )
    for clause in article.clauses:
        n = clause.number
        children.append(
            _Unit(
                clause.all_lines(),
                [n],
                [f"{n}.{p.letter}" for p in clause.points],
                children=[
                    _Unit(clause.lines, [n], []),
                    *(_Unit(p.lines, [n], [f"{n}.{p.letter}"]) for p in clause.points),
                ]
                if clause.points
                else [],
                continuation_line=f"Khoản {n}: {clause.lines[0][:160]}",
            )
        )
    whole = _Unit(
        article.all_lines()[1:],
        [c.number for c in article.clauses],
        [p for child in children for p in child.points],
        children=children,
    )
    return whole


def _context(prefix: str, lines: list[str]) -> str:
    return "\n".join([prefix, *lines])
