from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel
from qdrant_client.models import ScoredPoint

Stage = Literal["dense", "bm25", "fused", "rerank", "lookup"]


class RetrievedChunk(BaseModel):
    chunk_id: str
    document_id: str
    so_hieu: str
    path: str
    ordinal: int
    article_number: str
    article_title: str
    chapter_number: str | None
    chapter_title: str | None
    section_number: str | None
    section_title: str | None
    clauses: list[int]
    points: list[str]
    text: str
    context_text: str
    token_count: int
    valid_from: date | None
    valid_to: date | None
    score: float
    stage: Stage

    @classmethod
    def from_point(cls, point: ScoredPoint, stage: Stage) -> "RetrievedChunk":
        payload: dict[str, Any] = dict(point.payload or {})
        return cls.model_validate(
            {
                **payload,
                "valid_from": _date(payload.get("valid_from")),
                "valid_to": _date(payload.get("valid_to")),
                "score": point.score,
                "stage": stage,
            }
        )


def _date(value: str | None) -> date | None:
    return datetime.fromisoformat(value).date() if value else None
