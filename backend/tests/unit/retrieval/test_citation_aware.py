from datetime import date

from lawqa.retrieval.citation_lookup import CitationAwareRetriever
from lawqa.retrieval.types import RetrievedChunk
from lawqa.understanding.citation_regex import CitationRef
from tests.unit.pipelines.conftest import make_chunk


class FakeLookup:
    def __init__(self) -> None:
        self.refs: list[CitationRef] = []

    async def find(self, refs: list[CitationRef]) -> list[RetrievedChunk]:
        self.refs = refs
        return [
            make_chunk(ref.dieu, f"Điều {ref.dieu}", score=1.0).model_copy(
                update={"stage": "lookup"}
            )
            for ref in refs
        ]


class FakeRetriever:
    async def search(
        self, texts: list[str], reference_date: date, *, mode: str | None = None
    ) -> list[RetrievedChunk]:
        return [make_chunk("101", "gần đúng", score=0.9), make_chunk("100", "trùng", score=0.8)]


async def test_named_articles_come_first_without_duplicates() -> None:
    retriever = CitationAwareRetriever(FakeRetriever(), FakeLookup())

    result = await retriever.search(["Điều 100 quy định gì?"], date(2026, 10, 29))

    assert [(c.article_number, c.stage) for c in result] == [("100", "lookup"), ("101", "fused")]


async def test_questions_without_references_are_unchanged() -> None:
    lookup = FakeLookup()
    retriever = CitationAwareRetriever(FakeRetriever(), lookup)

    result = await retriever.search(["Điều kiện chuyển nhượng?"], date(2026, 10, 29))

    assert lookup.refs == []
    assert [c.article_number for c in result] == ["101", "100"]


async def test_lookup_can_be_disabled_for_ablation() -> None:
    lookup = FakeLookup()
    retriever = CitationAwareRetriever(FakeRetriever(), lookup, enabled=False)

    result = await retriever.search(["Điều 100"], date(2026, 10, 29))

    assert lookup.refs == []
    assert result[0].article_number == "101"
