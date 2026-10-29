import logging
import time
from collections.abc import AsyncIterator
from datetime import date
from typing import Protocol

from pydantic import BaseModel

from lawqa.generation.citations import validate_citations
from lawqa.generation.llm_client import (
    LLMError,
    LLMTimeoutError,
    LLMUnavailableError,
    Message,
)
from lawqa.generation.prompt_builder import build_messages
from lawqa.ingestion.chunker import TokenCounter
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
from lawqa.retrieval.context_packer import ContextSource, pack_context
from lawqa.retrieval.encoder_client import EncoderError
from lawqa.retrieval.types import RetrievedChunk

logger = logging.getLogger("lawqa.pipeline")

NO_BASIS_ANSWER = "Không tìm thấy căn cứ trong dữ liệu hiện có để trả lời câu hỏi này."


class Retriever(Protocol):
    async def search(self, texts: list[str], reference_date: date) -> list[RetrievedChunk]: ...


class StreamingLLM(Protocol):
    @property
    def model(self) -> str: ...

    def stream(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]: ...


class PipelineSettings(BaseModel):
    context_max_tokens: int = 6000
    max_answer_tokens: int = 1024
    max_chunks: int = 8


class HybridRAGPipeline:
    name = "hybrid"

    def __init__(
        self,
        *,
        retriever: Retriever,
        llm: StreamingLLM,
        counter: TokenCounter,
        settings: PipelineSettings,
    ) -> None:
        self._retriever = retriever
        self._llm = llm
        self._counter = counter
        self._settings = settings

    async def retrieve(self, query: Query) -> list[RetrievedChunk]:
        return await self._retriever.search([query.text], query.reference_date)

    async def answer(self, query: Query) -> AsyncIterator[PipelineEvent]:
        started = time.perf_counter()
        yield MetaEvent(query_id=query.query_id, pipeline=self.name)
        try:
            chunks = await self.retrieve(query)
            retrieved_at = time.perf_counter()
            best = sorted(chunks, key=lambda c: c.score, reverse=True)[: self._settings.max_chunks]
            sources = pack_context(best, self._counter, self._settings.context_max_tokens)
            yield SourcesEvent(sources=[_source(s) for s in sources])

            if not sources:
                yield DoneEvent(answer=NO_BASIS_ANSWER, citations=[], model=None)
                return

            pieces: list[str] = []
            first_token_at: float | None = None
            async for delta in self._llm.stream(
                build_messages(query.text, sources), max_tokens=self._settings.max_answer_tokens
            ):
                first_token_at = first_token_at or time.perf_counter()
                pieces.append(delta)
                yield TokenEvent(delta=delta)

            check = validate_citations("".join(pieces), len(sources))
            finished = time.perf_counter()
            yield DoneEvent(
                answer=check.text,
                citations=check.cited,
                invalid_citations=check.invalid,
                model=self._llm.model,
                latency_ms={
                    "retrieve": _ms(started, retrieved_at),
                    "ttft": _ms(started, first_token_at or finished),
                    "total": _ms(started, finished),
                },
            )
        except (EncoderError, LLMError) as error:
            logger.exception("pipeline.failed", extra={"query_id": query.query_id})
            yield _error_event(error)


def _source(source: ContextSource) -> Source:
    clauses = sorted({n for chunk in source.chunks for n in chunk.clauses})
    return Source(
        n=source.n,
        chunk_ids=[chunk.chunk_id for chunk in source.chunks],
        so_hieu=source.so_hieu,
        dieu=source.article_number,
        khoan=clauses,
        title=source.article_title,
        snippet=source.chunks[0].text[:200],
        score=source.score,
        context=source.text,
    )


def _error_event(error: Exception) -> ErrorEvent:
    if isinstance(error, EncoderError):
        return ErrorEvent(
            code="RETRIEVAL_UNAVAILABLE",
            message="Hệ thống tìm kiếm tạm thời không hoạt động, vui lòng thử lại sau.",
        )
    if isinstance(error, LLMTimeoutError):
        return ErrorEvent(
            code="LLM_TIMEOUT", message="Hệ thống trả lời quá lâu, vui lòng thử lại sau ít phút."
        )
    if isinstance(error, LLMUnavailableError):
        return ErrorEvent(
            code="LLM_UNAVAILABLE",
            message="Hệ thống trả lời tạm thời không hoạt động, vui lòng thử lại sau.",
        )
    return ErrorEvent(code="LLM_ERROR", message="Đã xảy ra lỗi khi tạo câu trả lời.")


def _ms(start: float, end: float) -> int:
    return round((end - start) * 1000)
