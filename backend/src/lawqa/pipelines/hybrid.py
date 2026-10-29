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
from lawqa.understanding.classifier import Understanding

logger = logging.getLogger("lawqa.pipeline")

NO_BASIS_ANSWER = "Không tìm thấy căn cứ trong dữ liệu hiện có để trả lời câu hỏi này."
OUT_OF_SCOPE_ANSWER = (
    "Hệ thống hiện chỉ hỗ trợ hỏi đáp về pháp luật đất đai. Câu hỏi của bạn nằm ngoài phạm vi này."
)


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


class Understander(Protocol):
    async def understand(self, question: str) -> Understanding: ...


class PipelineSettings(BaseModel):
    context_max_tokens: int = 6000
    max_answer_tokens: int = 1024
    max_chunks: int = 8
    # Reranker probability below which the best source is not considered a legal basis.
    min_rerank_score: float = 0.0
    # An "out of scope" verdict is overruled when retrieval still finds a source this strong.
    out_of_scope_override_score: float = 0.5
    # Off by default: on the seed set the rewrite lowered layperson recall@10 under rerank.
    search_with_legal_query: bool = False


class HybridRAGPipeline:
    name = "hybrid"

    def __init__(
        self,
        *,
        retriever: Retriever,
        llm: StreamingLLM,
        counter: TokenCounter,
        settings: PipelineSettings,
        understanding: Understander | None = None,
    ) -> None:
        self._understanding = understanding
        self._retriever = retriever
        self._llm = llm
        self._counter = counter
        self._settings = settings

    async def retrieve(self, query: Query) -> list[RetrievedChunk]:
        return await self._retriever.search([query.text], query.reference_date)

    async def _understand(self, query: Query) -> Understanding | None:
        return await self._understanding.understand(query.text) if self._understanding else None

    async def answer(self, query: Query) -> AsyncIterator[PipelineEvent]:
        started = time.perf_counter()
        understanding = await self._understand(query)
        understood_at = time.perf_counter()
        intent = understanding.intent if understanding else None
        missing_facts = understanding.missing_facts if understanding else []
        texts = [query.text]
        if (
            understanding
            and self._settings.search_with_legal_query
            and understanding.legal_query not in texts
        ):
            texts.append(understanding.legal_query)
        meta_sent = False
        try:
            chunks = await self._retriever.search(texts, query.reference_date)
            retrieved_at = time.perf_counter()
            if intent == "out_of_scope":
                # The classifier can be wrong about scope; trust it only when retrieval agrees.
                if not self._strong_source(chunks):
                    yield MetaEvent(query_id=query.query_id, pipeline=self.name, intent=intent)
                    yield SourcesEvent(sources=[])
                    yield DoneEvent(answer=OUT_OF_SCOPE_ANSWER, citations=[], model=None)
                    return
                logger.info("pipeline.out_of_scope_overruled", extra={"query_id": query.query_id})
                intent = "topic_search"
            yield MetaEvent(query_id=query.query_id, pipeline=self.name, intent=intent)
            meta_sent = True
            best = sorted(chunks, key=lambda c: c.score, reverse=True)[: self._settings.max_chunks]
            if (
                best
                and best[0].stage == "rerank"
                and best[0].score < self._settings.min_rerank_score
            ):
                logger.info(
                    "pipeline.no_basis",
                    extra={"query_id": query.query_id, "best_rerank_score": best[0].score},
                )
                best = []
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
                missing_facts=missing_facts,
                model=self._llm.model,
                latency_ms={
                    "understand": _ms(started, understood_at),
                    "retrieve": _ms(understood_at, retrieved_at),
                    "ttft": _ms(started, first_token_at or finished),
                    "total": _ms(started, finished),
                },
            )
        except (EncoderError, LLMError) as error:
            logger.exception("pipeline.failed", extra={"query_id": query.query_id})
            if not meta_sent:
                yield MetaEvent(query_id=query.query_id, pipeline=self.name, intent=intent)
            yield _error_event(error)

    def _strong_source(self, chunks: list[RetrievedChunk]) -> bool:
        best = max(chunks, key=lambda c: c.score, default=None)
        return (
            best is not None
            and best.stage in ("rerank", "lookup")
            and best.score >= self._settings.out_of_scope_override_score
        )


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
