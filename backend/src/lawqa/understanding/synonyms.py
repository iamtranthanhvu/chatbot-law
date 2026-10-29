import re
from datetime import date
from pathlib import Path
from typing import Protocol

import yaml

from lawqa.ingestion.normalize import normalize_text
from lawqa.retrieval.types import RetrievedChunk

DEFAULT_SYNONYMS = Path(__file__).resolve().parents[3] / "resources" / "dat_dai_synonyms.yaml"


class SynonymError(ValueError):
    pass


class SynonymDictionary:
    """Colloquial phrases → legal terms; replaces whole words, longest phrase first."""

    def __init__(self, mapping: dict[str, str]) -> None:
        self._mapping = mapping
        alternatives = sorted(mapping, key=len, reverse=True)
        self._pattern = re.compile(
            r"(?<![^\W_])(" + "|".join(re.escape(term) for term in alternatives) + r")(?![^\W_])",
            re.IGNORECASE,
        )

    @classmethod
    def load(cls, path: Path) -> "SynonymDictionary":
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        mapping: dict[str, str] = {}
        for entry in data.get("entries", []):
            legal = normalize_text(str(entry.get("legal", "")))
            terms = [normalize_text(str(term)).lower() for term in entry.get("terms", [])]
            if not legal or not terms or not all(terms):
                raise SynonymError(f"Mục từ điển rỗng hoặc thiếu: {entry}")
            for term in terms:
                if term in mapping:
                    raise SynonymError(f"Từ '{term}' xuất hiện ở hơn một mục")
                mapping[term] = legal
        return cls(mapping)

    def __len__(self) -> int:
        return len(self._mapping)

    def expand(self, text: str) -> str | None:
        """The question rewritten with legal terms, or None when nothing matched."""
        normalized = normalize_text(text)

        def replace(match: re.Match[str]) -> str:
            legal = self._mapping[match.group(0).lower()]
            if match.start() == 0 and match.group(0)[0].isupper():
                return legal[0].upper() + legal[1:]
            return legal

        expanded = self._pattern.sub(replace, normalized)
        return expanded if expanded != normalized else None


class ModeRetriever(Protocol):
    async def search(
        self, texts: list[str], reference_date: date, *, mode: str | None = None
    ) -> list[RetrievedChunk]: ...


class SynonymExpandingRetriever:
    """Adds the question rewritten with legal terms as an extra query text."""

    def __init__(
        self, inner: ModeRetriever, synonyms: SynonymDictionary, *, enabled: bool = True
    ) -> None:
        self._inner = inner
        self._synonyms = synonyms
        self._enabled = enabled

    async def search(
        self, texts: list[str], reference_date: date, *, mode: str | None = None
    ) -> list[RetrievedChunk]:
        queries = list(texts)
        if self._enabled:
            for text in texts:
                expanded = self._synonyms.expand(text)
                if expanded and expanded not in queries:
                    queries.append(expanded)
        return await self._inner.search(queries, reference_date, mode=mode)
