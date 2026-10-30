import json
from typing import Any

from lawqa.pipelines.base import (
    DoneEvent,
    ErrorEvent,
    MetaEvent,
    PipelineEvent,
    Source,
    SourcesEvent,
    TokenEvent,
)


def encode(name: str, data: Any) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def to_sse(event: PipelineEvent, *, cached: bool = False) -> str:
    """Pipeline events in the SPEC §3.6 wire format."""
    if isinstance(event, MetaEvent):
        return encode("meta", event.model_dump(exclude={"event"}))
    if isinstance(event, SourcesEvent):
        return encode("sources", [source_payload(s) for s in event.sources])
    if isinstance(event, TokenEvent):
        return encode("token", {"delta": event.delta})
    if isinstance(event, DoneEvent):
        return encode("done", done_payload(event, cached=cached))
    if isinstance(event, ErrorEvent):
        return encode("error", {"code": event.code, "message": event.message})
    raise TypeError(f"unknown pipeline event {event!r}")


def source_payload(source: Source) -> dict[str, Any]:
    return {
        "n": source.n,
        "chunk_id": source.chunk_ids[0],
        "chunk_ids": source.chunk_ids,
        "so_hieu": source.so_hieu,
        "dieu": source.dieu,
        "khoan": ", ".join(str(k) for k in source.khoan),
        "title": source.title,
        "snippet": source.snippet,
        "score": source.score,
    }


def done_payload(event: DoneEvent, *, cached: bool) -> dict[str, Any]:
    return {
        "answer": event.answer,
        "citations": event.citations,
        "invalid_citations": event.invalid_citations,
        "missing_facts": event.missing_facts,
        "usage": {},
        "latency_ms": event.latency_ms,
        "model": event.model,
        "disclaimer": event.disclaimer,
        "cached": cached,
    }
