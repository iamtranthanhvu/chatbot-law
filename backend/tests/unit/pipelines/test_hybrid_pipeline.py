from collections.abc import AsyncIterator
from datetime import date

from lawqa.generation.llm_client import LLMUnavailableError, Message
from lawqa.pipelines.base import (
    DoneEvent,
    ErrorEvent,
    MetaEvent,
    PipelineEvent,
    Query,
    SourcesEvent,
    TokenEvent,
)
from lawqa.pipelines.hybrid import HybridRAGPipeline, PipelineSettings
from lawqa.retrieval.types import RetrievedChunk
from tests.unit.pipelines.conftest import WordCounter, make_chunk

QUERY = Query(text="Điều kiện chuyển nhượng quyền sử dụng đất?", reference_date=date(2026, 10, 29))


class FakeRetriever:
    def __init__(self, chunks: list[RetrievedChunk]) -> None:
        self.chunks = chunks
        self.calls: list[tuple[list[str], date]] = []

    async def search(self, texts: list[str], reference_date: date) -> list[RetrievedChunk]:
        self.calls.append((texts, reference_date))
        return self.chunks


class FakeLLM:
    model = "fake-llm"

    def __init__(self, pieces: list[str], fail: bool = False) -> None:
        self.pieces = pieces
        self.fail = fail
        self.messages: list[Message] = []

    async def stream(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        self.messages = messages
        if self.fail:
            raise LLMUnavailableError("Không kết nối được LLM tại http://llm")
        for piece in self.pieces:
            yield piece


def _pipeline(retriever: FakeRetriever, llm: FakeLLM) -> HybridRAGPipeline:
    return HybridRAGPipeline(
        retriever=retriever,
        llm=llm,
        counter=WordCounter(),
        settings=PipelineSettings(context_max_tokens=1000, max_answer_tokens=256),
    )


async def _events(pipeline: HybridRAGPipeline, query: Query = QUERY) -> list[PipelineEvent]:
    return [event async for event in pipeline.answer(query)]


CHUNKS = [
    make_chunk("188", "Người sử dụng đất được chuyển nhượng khi có Giấy chứng nhận", score=0.9),
    make_chunk("167", "Quyền chuyển đổi, chuyển nhượng, cho thuê", score=0.7),
]


async def test_events_follow_the_sse_contract() -> None:
    llm = FakeLLM(["Cần có Giấy chứng nhận [2]", " và đất không tranh chấp [9]."])

    events = await _events(_pipeline(FakeRetriever(CHUNKS), llm))

    assert isinstance(events[0], MetaEvent)
    assert events[0].pipeline == "hybrid"
    assert events[0].query_id == QUERY.query_id
    assert isinstance(events[1], SourcesEvent)
    assert [s.n for s in events[1].sources] == [1, 2]
    assert [s.dieu for s in events[1].sources] == ["167", "188"]
    tokens = [e for e in events[2:-1] if isinstance(e, TokenEvent)]
    assert (
        "".join(t.delta for t in tokens)
        == "Cần có Giấy chứng nhận [2] và đất không tranh chấp [9]."
    )
    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert done.answer == "Cần có Giấy chứng nhận [2] và đất không tranh chấp."
    assert done.citations == [2]
    assert done.invalid_citations == [9]
    assert done.model == "fake-llm"
    assert {"retrieve", "ttft", "total"} <= set(done.latency_ms)
    assert done.disclaimer


async def test_prompt_contains_numbered_sources_and_the_question() -> None:
    llm = FakeLLM(["ok"])

    await _events(_pipeline(FakeRetriever(CHUNKS), llm))

    system, user = llm.messages
    assert system["role"] == "system" and "[n]" in system["content"]
    assert "[1] Luật Đất đai (45/2013/QH13) — Điều 167" in user["content"]
    assert "[2] Luật Đất đai (45/2013/QH13) — Điều 188" in user["content"]
    assert QUERY.text in user["content"]


async def test_reference_date_is_passed_to_retrieval() -> None:
    retriever = FakeRetriever(CHUNKS)

    await _events(_pipeline(retriever, FakeLLM(["ok"])))

    assert retriever.calls == [([QUERY.text], date(2026, 10, 29))]


async def test_no_sources_answers_without_calling_the_llm() -> None:
    llm = FakeLLM(["không được gọi"])

    events = await _events(_pipeline(FakeRetriever([]), llm))

    assert [type(e) for e in events] == [MetaEvent, SourcesEvent, DoneEvent]
    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert "Không tìm thấy căn cứ" in done.answer
    assert llm.messages == []


async def test_llm_failure_becomes_an_error_event() -> None:
    events = await _events(_pipeline(FakeRetriever(CHUNKS), FakeLLM([], fail=True)))

    assert [type(e) for e in events] == [MetaEvent, SourcesEvent, ErrorEvent]
    error = events[-1]
    assert isinstance(error, ErrorEvent)
    assert error.code == "LLM_UNAVAILABLE"
    assert "http://llm" not in error.message  # internal details are not shown to users


async def test_only_the_top_chunks_are_given_to_the_llm() -> None:
    many = [make_chunk(str(n), f"nội dung {n}", score=n / 100) for n in range(1, 21)]
    pipeline = HybridRAGPipeline(
        retriever=FakeRetriever(many),
        llm=FakeLLM(["ok [1]"]),
        counter=WordCounter(),
        settings=PipelineSettings(context_max_tokens=10_000, max_answer_tokens=256, max_chunks=5),
    )

    events = await _events(pipeline)

    sources = next(e for e in events if isinstance(e, SourcesEvent)).sources
    assert [s.dieu for s in sources] == ["16", "17", "18", "19", "20"]


async def test_prompt_demands_bracket_citations_and_forbids_outside_documents() -> None:
    llm = FakeLLM(["ok"])

    await _events(_pipeline(FakeRetriever(CHUNKS), llm))

    system, user = llm.messages
    assert "[2]." in system["content"]  # worked example of a cited sentence
    assert "không có trong NGUỒN" in system["content"]
    assert user["content"].rstrip().endswith("mỗi ý phải kèm số nguồn [n].")


async def test_weak_best_rerank_score_refuses_without_calling_the_llm() -> None:
    weak = [
        make_chunk("64", "thu hồi đất", score=0.02).model_copy(update={"stage": "rerank"}),
        make_chunk("77", "bồi thường", score=0.01).model_copy(update={"stage": "rerank"}),
    ]
    llm = FakeLLM(["không được gọi"])
    pipeline = HybridRAGPipeline(
        retriever=FakeRetriever(weak),
        llm=llm,
        counter=WordCounter(),
        settings=PipelineSettings(min_rerank_score=0.1),
    )

    events = await _events(pipeline)

    assert [type(e) for e in events] == [MetaEvent, SourcesEvent, DoneEvent]
    assert isinstance(events[1], SourcesEvent) and events[1].sources == []
    done = events[-1]
    assert isinstance(done, DoneEvent) and "Không tìm thấy căn cứ" in done.answer
    assert llm.messages == []


async def test_threshold_does_not_apply_to_scores_from_other_stages() -> None:
    llm = FakeLLM(["ok [1]"])
    pipeline = HybridRAGPipeline(
        retriever=FakeRetriever([make_chunk("1", "x", score=0.01)]),  # RRF scores are tiny
        llm=llm,
        counter=WordCounter(),
        settings=PipelineSettings(min_rerank_score=0.1),
    )

    events = await _events(pipeline)

    assert isinstance(events[-1], DoneEvent) and events[-1].citations == [1]
