import asyncio
import time
from collections.abc import AsyncIterator

import httpx
import pytest
from redis.asyncio import Redis

from lawqa.api.concurrency import GenerationSlots
from lawqa.api.deps import AppContainer
from lawqa.core.cache import AnswerCache, normalize_question
from lawqa.core.rate_limit import RateLimit, RateLimiter
from lawqa.main import create_app
from tests.unit.api.test_ask import FakePipeline, FakeQueryStore, parse_sse

pytestmark = pytest.mark.integration


def _app(
    redis: Redis,
    pipeline: FakePipeline,
    store: FakeQueryStore,
    *,
    limits: tuple[RateLimit, ...] = (RateLimit(10, 60), RateLimit(100, 86400)),
    slots: GenerationSlots | None = None,
) -> AppContainer:
    return AppContainer(
        pipeline=pipeline,
        query_store=store,
        ip_hash_secret="bí mật",
        config_hash="cfg123",
        git_sha="abc1234",
        rate_limiter=RateLimiter(redis, limits),
        answer_cache=AnswerCache(redis, ttl_seconds=60),
        slots=slots or GenerationSlots(max_concurrent=4, wait_seconds=1),
    )


async def _client(container: AppContainer) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_app(container))
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
        yield client


async def test_the_eleventh_question_in_a_minute_is_429_with_retry_after(redis: Redis) -> None:
    container = _app(redis, FakePipeline(), FakeQueryStore())
    async for client in _client(container):
        statuses = [
            (await client.post("/api/v1/ask", json={"question": f"câu {i}"})).status_code
            for i in range(10)
        ]
        blocked = await client.post("/api/v1/ask", json={"question": "câu 11"})

    assert statuses == [200] * 10
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RATE_LIMITED"
    assert 0 < int(blocked.headers["retry-after"]) <= 60


async def test_the_daily_limit_applies_too(redis: Redis) -> None:
    container = _app(
        redis,
        FakePipeline(),
        FakeQueryStore(),
        limits=(RateLimit(10, 60), RateLimit(2, 86400)),
    )
    async for client in _client(container):
        for i in range(2):
            await client.post("/api/v1/ask", json={"question": f"câu {i}"})
        blocked = await client.post("/api/v1/ask", json={"question": "câu 3"})

    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 60


async def test_over_the_concurrency_limit_answers_busy_instead_of_hanging(redis: Redis) -> None:
    store = FakeQueryStore()
    container = _app(
        redis,
        FakePipeline(delay=1.0),
        store,
        slots=GenerationSlots(max_concurrent=1, wait_seconds=0.2),
    )
    async for client in _client(container):
        started = time.perf_counter()
        slow, busy = await asyncio.gather(
            client.post("/api/v1/ask", json={"question": "câu chậm"}),
            client.post("/api/v1/ask", json={"question": "câu khác"}),
        )

    names = {name for name, _ in parse_sse(slow.text)} | {n for n, _ in parse_sse(busy.text)}
    errors = [data for r in (slow, busy) for name, data in parse_sse(r.text) if name == "error"]
    assert "done" in names
    assert errors == [
        {"code": "BUSY", "message": "Hệ thống đang bận, vui lòng thử lại sau ít phút."}
    ]
    assert time.perf_counter() - started < 3
    assert sorted(r.outcome for r in store.records) == ["done", "error"]


async def test_the_same_question_again_is_served_from_the_cache(redis: Redis) -> None:
    pipeline, store = FakePipeline(), FakeQueryStore()
    async for client in _client(_app(redis, pipeline, store)):
        first = parse_sse((await client.post("/api/v1/ask", json={"question": "Cấp sổ?"})).text)
        again = parse_sse(
            (await client.post("/api/v1/ask", json={"question": "  cấp   SỔ? "})).text
        )

    assert len(pipeline.queries) == 1
    assert [name for name, _ in again] == ["meta", "sources", "token", "done"]
    assert again[-1][1]["cached"] is True
    assert again[-1][1]["answer"] == first[-1][1]["answer"]
    assert again[1][1] == first[1][1]
    assert again[0][1]["query_id"] != first[0][1]["query_id"]
    assert [r.cached for r in store.records] == [False, True]


async def test_a_new_corpus_version_does_not_reuse_old_answers(redis: Redis) -> None:
    pipeline, store = FakePipeline(), FakeQueryStore()
    async for client in _client(_app(redis, pipeline, store)):
        await client.post("/api/v1/ask", json={"question": "Cấp sổ?"})
        store.version = 8  # what `lawqa ingest --replace` does
        again = parse_sse((await client.post("/api/v1/ask", json={"question": "Cấp sổ?"})).text)

    assert len(pipeline.queries) == 2
    assert again[-1][1]["cached"] is False


async def test_errors_are_not_cached(redis: Redis) -> None:
    from lawqa.pipelines.base import ErrorEvent

    pipeline = FakePipeline(tail=[ErrorEvent(code="LLM_TIMEOUT", message="lâu")])
    async for client in _client(_app(redis, pipeline, FakeQueryStore())):
        await client.post("/api/v1/ask", json={"question": "Cấp sổ?"})
        await client.post("/api/v1/ask", json={"question": "Cấp sổ?"})

    assert len(pipeline.queries) == 2


def test_question_normalization_ignores_case_spacing_and_end_punctuation() -> None:
    assert normalize_question("  Cấp   SỔ đỏ ?? ") == normalize_question("cấp sổ đỏ")
    assert normalize_question("cấp sổ đỏ") != normalize_question("cấp sổ hồng")


async def test_the_limit_holds_across_a_clock_minute_boundary(
    redis: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    import lawqa.core.rate_limit as rate_limit

    clock = iter([59.0, 59.5, 60.5])
    monkeypatch.setattr(rate_limit.time, "time", lambda: next(clock))
    limiter = RateLimiter(redis, (RateLimit(2, 60),))

    decisions = [await limiter.hit("ip") for _ in range(3)]

    assert [d.allowed for d in decisions] == [True, True, False]
    assert decisions[-1].retry_after == 59


async def test_refused_requests_do_not_extend_the_wait(
    redis: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    import lawqa.core.rate_limit as rate_limit

    clock = iter([0.0, 1.0, 30.0, 61.0])
    monkeypatch.setattr(rate_limit.time, "time", lambda: next(clock))
    limiter = RateLimiter(redis, (RateLimit(2, 60),))

    decisions = [await limiter.hit("ip") for _ in range(4)]

    assert [d.allowed for d in decisions] == [True, True, False, True]
