from datetime import date

from lawqa.retrieval.rerank import Reranker, RerankingRetriever, RerankSettings
from lawqa.retrieval.types import RetrievedChunk
from tests.unit.pipelines.conftest import make_chunk


class FakeScorer:
    def __init__(self, table: dict[tuple[str, str], float]) -> None:
        self.table = table
        self.passages: list[str] = []

    async def rerank(self, query: str, passages: list[str]) -> list[float]:
        self.passages = passages
        return [self.table.get((query, p.splitlines()[-1]), 0.0) for p in passages]


CHUNKS = [
    make_chunk("1", "một", score=0.9),
    make_chunk("2", "hai", score=0.5),
    make_chunk("3", "ba"),
]


async def test_reorders_by_reranker_score_and_keeps_top_n() -> None:
    scorer = FakeScorer({("q", "một"): 0.1, ("q", "hai"): 0.8, ("q", "ba"): 0.4})

    result = await Reranker(scorer, RerankSettings(top_n=2)).rerank(["q"], CHUNKS)

    assert [c.article_number for c in result] == ["2", "3"]
    assert [c.score for c in result] == [0.8, 0.4]
    assert {c.stage for c in result} == {"rerank"}


async def test_reranker_sees_the_breadcrumb_context() -> None:
    scorer = FakeScorer({})

    await Reranker(scorer, RerankSettings()).rerank(["q"], CHUNKS[:1])

    assert scorer.passages[0].startswith("Luật Đất đai (45/2013/QH13) > Điều 1")


async def test_best_score_over_several_query_texts_wins() -> None:
    scorer = FakeScorer({("q1", "một"): 0.2, ("q2", "một"): 0.7, ("q1", "hai"): 0.5})

    result = await Reranker(scorer, RerankSettings(top_n=2)).rerank(["q1", "q2"], CHUNKS[:2])

    assert [(c.article_number, c.score) for c in result] == [("1", 0.7), ("2", 0.5)]


async def test_nothing_to_rerank() -> None:
    assert await Reranker(FakeScorer({}), RerankSettings()).rerank(["q"], []) == []


class FakeRetriever:
    def __init__(self) -> None:
        self.modes: list[str] = []

    async def search(
        self, texts: list[str], reference_date: date, *, mode: str | None = None
    ) -> list[RetrievedChunk]:
        self.modes.append(mode or "default")
        return CHUNKS


async def test_rerank_suffix_selects_first_stage_mode_then_reranks() -> None:
    retriever = FakeRetriever()
    scorer = FakeScorer({("q", "ba"): 0.9})
    ranked = RerankingRetriever(retriever, Reranker(scorer, RerankSettings(top_n=1)))

    reranked = await ranked.search(["q"], date(2026, 10, 29), mode="hybrid+rerank")
    plain = await ranked.search(["q"], date(2026, 10, 29), mode="dense")

    assert retriever.modes == ["hybrid", "dense"]
    assert [c.article_number for c in reranked] == ["3"]
    assert len(plain) == 3 and plain[0].stage == "fused"


async def test_default_mode_reranks_hybrid_results() -> None:
    retriever = FakeRetriever()
    ranked = RerankingRetriever(retriever, Reranker(FakeScorer({}), RerankSettings(top_n=2)))

    result = await ranked.search(["q"], date(2026, 10, 29))

    assert retriever.modes == ["hybrid"]
    assert len(result) == 2 and result[0].stage == "rerank"


async def test_only_the_first_candidates_are_sent_to_the_reranker() -> None:
    scorer = FakeScorer({})

    result = await Reranker(scorer, RerankSettings(top_n=8, candidates=2)).rerank(["q"], CHUNKS)

    assert len(scorer.passages) == 2
    assert [c.article_number for c in result] == ["1", "2"]
