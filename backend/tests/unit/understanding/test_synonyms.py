import unicodedata
from datetime import date
from pathlib import Path

import pytest

from lawqa.retrieval.types import RetrievedChunk
from lawqa.understanding.synonyms import (
    DEFAULT_SYNONYMS,
    SynonymDictionary,
    SynonymError,
    SynonymExpandingRetriever,
)


@pytest.fixture(scope="module")
def synonyms() -> SynonymDictionary:
    return SynonymDictionary.load(DEFAULT_SYNONYMS)


def test_shipped_dictionary_is_valid_and_reasonably_large(synonyms: SynonymDictionary) -> None:
    assert len(synonyms) >= 40


@pytest.mark.parametrize(
    ("question", "expanded"),
    [
        (
            "Làm sổ đỏ lần đầu cần giấy tờ gì?",
            "Làm giấy chứng nhận quyền sử dụng đất lần đầu cần giấy tờ gì?",
        ),
        ("Đất thổ cư được sử dụng trong bao lâu?", "Đất ở được sử dụng trong bao lâu?"),
        ("Bị lấy đất thì được đền bù không?", "Bị thu hồi đất thì được bồi thường không?"),
    ],
)
def test_colloquial_terms_are_replaced_by_legal_terms(
    synonyms: SynonymDictionary, question: str, expanded: str
) -> None:
    assert synonyms.expand(question) == expanded


def test_longest_term_wins(synonyms: SynonymDictionary) -> None:
    assert synonyms.expand("Muốn chuyển lên thổ cư thì làm sao?") == (
        "Muốn chuyển mục đích sử dụng đất sang đất ở thì làm sao?"
    )


def test_matching_ignores_case_and_unicode_form(synonyms: SynonymDictionary) -> None:
    question = unicodedata.normalize("NFD", "SỔ ĐỎ bị mất thì sao?")

    assert synonyms.expand(question) == "Giấy chứng nhận quyền sử dụng đất bị mất thì sao?"


def test_terms_are_whole_words_only(synonyms: SynonymDictionary) -> None:
    assert synonyms.expand("Điều kiện chuyển nhượng quyền sử dụng đất") is None


def test_duplicate_terms_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(
        "entries:\n"
        "  - {legal: đất ở, terms: [thổ cư]}\n"
        "  - {legal: đất nông nghiệp, terms: [thổ cư]}\n",
        encoding="utf-8",
    )

    with pytest.raises(SynonymError, match="thổ cư"):
        SynonymDictionary.load(path)


def test_empty_entries_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("entries:\n  - {legal: '', terms: [x]}\n", encoding="utf-8")

    with pytest.raises(SynonymError):
        SynonymDictionary.load(path)


class Recorder:
    def __init__(self) -> None:
        self.texts: list[str] = []

    async def search(
        self, texts: list[str], reference_date: date, *, mode: str | None = None
    ) -> list[RetrievedChunk]:
        self.texts = texts
        return []


async def test_retriever_searches_with_the_original_and_the_expanded_question(
    synonyms: SynonymDictionary,
) -> None:
    inner = Recorder()

    await SynonymExpandingRetriever(inner, synonyms).search(["Sổ đỏ là gì?"], date(2026, 1, 1))

    assert inner.texts == ["Sổ đỏ là gì?", "Giấy chứng nhận quyền sử dụng đất là gì?"]


async def test_disabled_or_nothing_to_expand_keeps_the_query(synonyms: SynonymDictionary) -> None:
    inner = Recorder()

    await SynonymExpandingRetriever(inner, synonyms, enabled=False).search(["Sổ đỏ?"], date.today())
    assert inner.texts == ["Sổ đỏ?"]

    await SynonymExpandingRetriever(inner, synonyms).search(["Điều 100?"], date.today())
    assert inner.texts == ["Điều 100?"]
