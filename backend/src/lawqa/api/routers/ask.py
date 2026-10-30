import time
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Literal

import anyio
import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, StringConstraints

from lawqa.api.concurrency import BusyError, GenerationSlots
from lawqa.api.deps import (
    AnsweringPipeline,
    AppContainer,
    get_container,
    get_pipeline,
    get_query_store,
)
from lawqa.api.sse import source_payload, to_sse
from lawqa.core.cache import AnswerCache, CachedAnswer
from lawqa.core.errors import NotFoundError, RateLimitedError
from lawqa.core.privacy import ip_hash
from lawqa.db.queries import QueryRecord, QueryStore
from lawqa.pipelines.base import (
    DoneEvent,
    ErrorEvent,
    MetaEvent,
    PipelineEvent,
    Query,
    SourcesEvent,
    TokenEvent,
)

router = APIRouter(tags=["ask"])
logger = structlog.get_logger("lawqa.api")

MAX_QUESTION_CHARS = 1000
INTERNAL_ERROR = ErrorEvent(code="INTERNAL_ERROR", message="Đã xảy ra lỗi khi tạo câu trả lời.")
BUSY = ErrorEvent(code="BUSY", message="Hệ thống đang bận, vui lòng thử lại sau ít phút.")

Container = Annotated[AppContainer, Depends(get_container)]
Pipeline = Annotated[AnsweringPipeline, Depends(get_pipeline)]
Store = Annotated[QueryStore, Depends(get_query_store)]


class AskRequest(BaseModel):
    question: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_QUESTION_CHARS)
    ]


class FeedbackRequest(BaseModel):
    rating: Literal["up", "down"]
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None = None


@router.post("/ask")
async def ask(
    body: AskRequest, request: Request, container: Container, pipeline: Pipeline, store: Store
) -> StreamingResponse:
    query = Query(text=body.question)
    client = ip_hash(container.ip_hash_secret, client_ip(request))
    if container.rate_limiter is not None:
        # Redis trouble lets requests through: answering beats protecting here.
        try:
            decision = await container.rate_limiter.hit(client)
        except Exception:
            logger.warning("rate_limit.unavailable", exc_info=True)
        else:
            if not decision.allowed:
                raise RateLimitedError(decision.retry_after)

    corpus_version = await store.corpus_version()
    record = QueryRecord(
        id=uuid.UUID(query.query_id),
        question=query.text,
        pipeline=pipeline.name,
        config_hash=container.config_hash,
        corpus_version=corpus_version,
        git_sha=container.git_sha,
        ip_hash=client,
    )
    cache = container.answer_cache
    cache_key = (
        cache.key(query.text, pipeline.name, container.config_hash, corpus_version) if cache else ""
    )
    cached = await _cached_quietly(cache, cache_key) if cache else None
    record.cached = cached is not None
    events = (
        _replay(cached, query, pipeline.name)
        if cached
        else _generate(pipeline, query, container.slots, cache, cache_key)
    )
    return StreamingResponse(
        _stream(events, query, record, store),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/queries/{query_id}/feedback")
async def feedback(query_id: uuid.UUID, body: FeedbackRequest, store: Store) -> dict[str, str]:
    if not await store.add_feedback(query_id, body.rating, body.note or None):
        raise NotFoundError("Không tìm thấy câu hỏi.")
    return {"status": "ok"}


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _generate(
    pipeline: AnsweringPipeline,
    query: Query,
    slots: GenerationSlots | None,
    cache: AnswerCache | None,
    cache_key: str,
) -> AsyncIterator[PipelineEvent]:
    try:
        async with slots.slot() if slots else _no_limit():
            intent: str | None = None
            sources: SourcesEvent | None = None
            async for event in pipeline.answer(query):
                if isinstance(event, MetaEvent):
                    intent = event.intent
                elif isinstance(event, SourcesEvent):
                    sources = event
                elif isinstance(event, DoneEvent) and cache and sources is not None:
                    answer = CachedAnswer(intent=intent, sources=sources.sources, done=event)
                    await _cache_quietly(cache, cache_key, answer)
                yield event
    except BusyError:
        logger.warning("ask.busy")
        yield BUSY


async def _replay(
    cached: CachedAnswer, query: Query, pipeline: str
) -> AsyncIterator[PipelineEvent]:
    started = time.perf_counter()
    yield MetaEvent(query_id=query.query_id, pipeline=pipeline, intent=cached.intent)
    yield SourcesEvent(sources=cached.sources)
    if cached.done.answer:
        yield TokenEvent(delta=cached.done.answer)
    elapsed = round((time.perf_counter() - started) * 1000)
    yield cached.done.model_copy(update={"latency_ms": {"total": elapsed}})


async def _stream(
    events: AsyncIterator[PipelineEvent], query: Query, record: QueryRecord, store: QueryStore
) -> AsyncIterator[str]:
    """A client disconnect cancels this generator, which closes the pipeline (and its LLM
    stream); the query is still logged, as "cancelled"."""
    with structlog.contextvars.bound_contextvars(query_id=query.query_id):
        try:
            async for event in events:
                _note(record, event)
                yield to_sse(event, cached=record.cached)
        except Exception:
            logger.exception("ask.failed")
            _note(record, INTERNAL_ERROR)
            yield to_sse(INTERNAL_ERROR)
        finally:
            with anyio.CancelScope(shield=True):
                try:
                    await store.save(record)
                except Exception:
                    logger.exception("query_log.failed")


async def _cached_quietly(cache: AnswerCache, key: str) -> CachedAnswer | None:
    try:
        return await cache.get(key)
    except Exception:
        logger.warning("answer_cache.read_failed", exc_info=True)
        return None


async def _cache_quietly(cache: AnswerCache, key: str, answer: CachedAnswer) -> None:
    try:
        await cache.set(key, answer)
    except Exception:
        logger.warning("answer_cache.write_failed", exc_info=True)


class _no_limit:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *exc: object) -> None:
        return None


def _note(record: QueryRecord, event: PipelineEvent) -> None:
    if isinstance(event, MetaEvent):
        record.intent = event.intent
    elif isinstance(event, SourcesEvent):
        record.sources = [source_payload(s) for s in event.sources]
    elif isinstance(event, DoneEvent):
        record.outcome = "done"
        record.answer = event.answer
        record.citations = event.citations
        record.invalid_citations = event.invalid_citations
        record.missing_facts = event.missing_facts
        record.latency_ms = event.latency_ms
        record.model = event.model
        record.legal_query = event.trace.get("legal_query")
        record.retrieved = event.trace.get("retrieved", [])
    elif isinstance(event, ErrorEvent):
        record.outcome = "error"
        record.error_code = event.code
