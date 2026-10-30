import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from lawqa.api.deps import AppContainer
from lawqa.db.queries import QueryRecord
from lawqa.main import create_app
from lawqa.pipelines.base import (
    DoneEvent,
    ErrorEvent,
    MetaEvent,
    PipelineEvent,
    Query,
    Source,
    SourcesEvent,
    TokenEvent,
)

SOURCE = Source(
    n=1,
    chunk_ids=["c-100", "c-100b"],
    so_hieu="45/2013/QH13",
    dieu="100",
    khoan=[1, 2],
    title="Cấp Giấy chứng nhận",
    snippet="1. Hộ gia đình…",
    score=0.91,
    context="toàn văn nội bộ",
)


class FakePipeline:
    name = "hybrid"

    def __init__(self, tail: list[PipelineEvent] | None = None, delay: float = 0.0) -> None:
        self.tail = tail
        self.delay = delay
        self.queries: list[Query] = []
        self.closed = False

    async def answer(self, query: Query) -> AsyncIterator[PipelineEvent]:
        self.queries.append(query)
        try:
            yield MetaEvent(query_id=query.query_id, pipeline=self.name, intent="situation")
            yield SourcesEvent(sources=[SOURCE])
            if self.tail is not None:
                for event in self.tail:
                    yield event
                return
            for piece in ["Được ", "cấp [1]."]:
                await asyncio.sleep(self.delay)
                yield TokenEvent(delta=piece)
            yield DoneEvent(
                answer="Được cấp [1].",
                citations=[1],
                missing_facts=["Đất có tranh chấp không"],
                model="fake",
                latency_ms={"total": 5},
                trace={"legal_query": "cấp giấy chứng nhận", "retrieved": []},
            )
        finally:
            self.closed = True


class FakeQueryStore:
    def __init__(self) -> None:
        self.records: list[QueryRecord] = []
        self.feedback: dict[uuid.UUID, tuple[str, str | None]] = {}

    async def corpus_version(self) -> int:
        return 7

    async def save(self, record: QueryRecord) -> None:
        self.records.append(record)

    async def add_feedback(self, query_id: uuid.UUID, rating: str, note: str | None) -> bool:
        if all(r.id != query_id for r in self.records):
            return False
        self.feedback[query_id] = (rating, note)
        return True


def _container(pipeline: FakePipeline, store: FakeQueryStore) -> AppContainer:
    return AppContainer(
        pipeline=pipeline,
        query_store=store,
        ip_hash_secret="bí mật",
        config_hash="cfg123",
        git_sha="abc1234",
    )


def parse_sse(body: str) -> list[tuple[str, Any]]:
    events = []
    for block in body.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((fields["event"], json.loads(fields["data"])))
    return events


@pytest.fixture
def store() -> FakeQueryStore:
    return FakeQueryStore()


async def _post(pipeline: FakePipeline, store: FakeQueryStore, question: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=create_app(_container(pipeline, store)))
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
        return await client.post("/api/v1/ask", json={"question": question})


async def test_ask_streams_meta_sources_tokens_done(store: FakeQueryStore) -> None:
    response = await _post(FakePipeline(), store, "Tôi có được cấp sổ đỏ không?")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["meta", "sources", "token", "token", "done"]
    meta, sources, done = events[0][1], events[1][1], events[-1][1]
    assert meta["pipeline"] == "hybrid" and meta["intent"] == "situation"
    assert sources == [
        {
            "n": 1,
            "chunk_id": "c-100",
            "chunk_ids": ["c-100", "c-100b"],
            "so_hieu": "45/2013/QH13",
            "dieu": "100",
            "khoan": "1, 2",
            "title": "Cấp Giấy chứng nhận",
            "snippet": "1. Hộ gia đình…",
            "score": 0.91,
        }
    ]
    assert done["citations"] == [1]
    assert done["missing_facts"] == ["Đất có tranh chấp không"]
    assert done["cached"] is False
    assert "usage" in done and "latency_ms" in done and "disclaimer" in done
    assert "trace" not in done


async def test_the_query_is_logged_after_the_stream_without_the_raw_ip(
    store: FakeQueryStore,
) -> None:
    response = await _post(FakePipeline(), store, "  Tôi có được cấp sổ đỏ không?  ")

    meta = parse_sse(response.text)[0][1]
    [record] = store.records
    assert str(record.id) == meta["query_id"]
    assert record.question == "Tôi có được cấp sổ đỏ không?"
    assert record.outcome == "done"
    assert record.intent == "situation"
    assert record.legal_query == "cấp giấy chứng nhận"
    assert record.corpus_version == 7
    assert record.config_hash == "cfg123" and record.git_sha == "abc1234"
    assert record.sources[0]["chunk_ids"] == ["c-100", "c-100b"]
    assert len(record.ip_hash) == 64
    assert "127.0.0.1" not in record.model_dump_json()


async def test_llm_failure_ends_the_stream_with_an_error_event(store: FakeQueryStore) -> None:
    pipeline = FakePipeline(tail=[ErrorEvent(code="LLM_UNAVAILABLE", message="tạm thời lỗi")])

    events = parse_sse((await _post(pipeline, store, "Hỏi gì đó")).text)

    assert [name for name, _ in events] == ["meta", "sources", "error"]
    assert events[-1][1] == {"code": "LLM_UNAVAILABLE", "message": "tạm thời lỗi"}
    assert store.records[0].outcome == "error"
    assert store.records[0].error_code == "LLM_UNAVAILABLE"


@pytest.mark.parametrize("question", ["", "   ", "x" * 1001])
async def test_empty_or_too_long_questions_are_rejected(
    store: FakeQueryStore, question: str
) -> None:
    pipeline = FakePipeline()

    response = await _post(pipeline, store, question)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert pipeline.queries == []


async def test_a_client_disconnect_cancels_generation(store: FakeQueryStore) -> None:
    pipeline = FakePipeline(delay=0.2)
    app = create_app(_container(pipeline, store))
    body = json.dumps({"question": "Hỏi gì đó"}).encode()
    request_sent = False
    first_chunk = asyncio.Event()

    async def receive() -> dict[str, Any]:
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        await first_chunk.wait()
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.body" and message.get("body"):
            first_chunk.set()

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "path": "/api/v1/ask",
        "raw_path": b"/api/v1/ask",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
        "client": ("10.0.0.1", 1234),
        "server": ("api", 80),
        "scheme": "http",
        "root_path": "",
    }
    await asyncio.wait_for(app(scope, receive, send), timeout=5)

    assert pipeline.closed
    [record] = store.records
    assert record.outcome == "cancelled"
    assert record.answer == ""


async def test_feedback_is_saved_for_a_logged_query(store: FakeQueryStore) -> None:
    pipeline = FakePipeline()
    transport = httpx.ASGITransport(app=create_app(_container(pipeline, store)))
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
        events = parse_sse((await client.post("/api/v1/ask", json={"question": "q"})).text)
        query_id = events[0][1]["query_id"]

        response = await client.post(
            f"/api/v1/queries/{query_id}/feedback", json={"rating": "down", "note": "thiếu"}
        )

    assert response.status_code == 200
    assert store.feedback[uuid.UUID(query_id)] == ("down", "thiếu")


async def test_feedback_for_an_unknown_query_is_404(store: FakeQueryStore) -> None:
    transport = httpx.ASGITransport(app=create_app(_container(FakePipeline(), store)))
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
        response = await client.post(
            f"/api/v1/queries/{uuid.uuid4()}/feedback", json={"rating": "up"}
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
