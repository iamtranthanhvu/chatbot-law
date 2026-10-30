import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Literal

import anyio
import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, StringConstraints

from lawqa.api.deps import (
    AnsweringPipeline,
    AppContainer,
    get_container,
    get_pipeline,
    get_query_store,
)
from lawqa.api.sse import source_payload, to_sse
from lawqa.core.errors import NotFoundError
from lawqa.core.privacy import ip_hash
from lawqa.db.queries import QueryRecord, QueryStore
from lawqa.pipelines.base import (
    DoneEvent,
    ErrorEvent,
    MetaEvent,
    PipelineEvent,
    Query,
    SourcesEvent,
)

router = APIRouter(tags=["ask"])
logger = structlog.get_logger("lawqa.api")

MAX_QUESTION_CHARS = 1000
INTERNAL_ERROR = ErrorEvent(code="INTERNAL_ERROR", message="Đã xảy ra lỗi khi tạo câu trả lời.")

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
    record = QueryRecord(
        id=uuid.UUID(query.query_id),
        question=query.text,
        pipeline=pipeline.name,
        config_hash=container.config_hash,
        corpus_version=await store.corpus_version(),
        git_sha=container.git_sha,
        ip_hash=ip_hash(container.ip_hash_secret, client_ip(request)),
    )
    return StreamingResponse(
        _stream(pipeline, query, record, store),
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


async def _stream(
    pipeline: AnsweringPipeline, query: Query, record: QueryRecord, store: QueryStore
) -> AsyncIterator[str]:
    """A client disconnect cancels this generator, which closes the pipeline (and its LLM
    stream); the query is still logged, as "cancelled"."""
    with structlog.contextvars.bound_contextvars(query_id=query.query_id):
        try:
            async for event in pipeline.answer(query):
                _note(record, event)
                yield to_sse(event)
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
