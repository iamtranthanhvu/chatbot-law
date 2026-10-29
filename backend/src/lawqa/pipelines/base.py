import uuid
from collections.abc import AsyncIterator
from datetime import date
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, Field

from lawqa.retrieval.types import RetrievedChunk

DISCLAIMER = "Thông tin chỉ mang tính tham khảo, không thay thế tư vấn pháp lý."


class Query(BaseModel):
    text: str
    reference_date: date = Field(default_factory=date.today)
    query_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class Source(BaseModel):
    n: int
    chunk_ids: list[str]
    so_hieu: str
    dieu: str
    khoan: list[int]
    title: str
    snippet: str
    score: float
    # Full source text given to the LLM; used by evaluation, never sent to end users.
    context: str = Field(default="", exclude=True)


class MetaEvent(BaseModel):
    event: Literal["meta"] = "meta"
    query_id: str
    pipeline: str
    intent: str | None = None


class SourcesEvent(BaseModel):
    event: Literal["sources"] = "sources"
    sources: list[Source]


class TokenEvent(BaseModel):
    event: Literal["token"] = "token"
    delta: str


class DoneEvent(BaseModel):
    event: Literal["done"] = "done"
    answer: str
    citations: list[int]
    invalid_citations: list[int] = Field(default_factory=list)
    model: str | None = None
    latency_ms: dict[str, int] = Field(default_factory=dict)
    disclaimer: str = DISCLAIMER


class ErrorEvent(BaseModel):
    event: Literal["error"] = "error"
    code: str
    message: str


PipelineEvent = Annotated[
    MetaEvent | SourcesEvent | TokenEvent | DoneEvent | ErrorEvent, Field(discriminator="event")
]


class RAGPipeline(Protocol):
    """Contract shared by the three approaches (hybrid, hybrid_graph, agentic)."""

    name: str

    async def retrieve(self, query: Query) -> list[RetrievedChunk]: ...

    def answer(self, query: Query) -> AsyncIterator[PipelineEvent]: ...
