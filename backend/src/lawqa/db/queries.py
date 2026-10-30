import uuid
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lawqa.db.models import CorpusState, Feedback, QueryLog

Outcome = Literal["done", "error", "cancelled"]
Rating = Literal["up", "down"]


class QueryRecord(BaseModel):
    id: uuid.UUID
    question: str
    intent: str | None = None
    legal_query: str | None = None
    pipeline: str
    config_hash: str
    corpus_version: int
    sources: list[dict[str, Any]] = Field(default_factory=list)
    retrieved: list[dict[str, Any]] = Field(default_factory=list)
    answer: str = ""
    citations: list[int] = Field(default_factory=list)
    invalid_citations: list[int] = Field(default_factory=list)
    missing_facts: list[str] = Field(default_factory=list)
    latency_ms: dict[str, int] = Field(default_factory=dict)
    usage: dict[str, int] = Field(default_factory=dict)
    model: str | None = None
    git_sha: str
    cached: bool = False
    outcome: Outcome = "cancelled"
    error_code: str | None = None
    ip_hash: str


class QueryStore(Protocol):
    async def corpus_version(self) -> int: ...

    async def save(self, record: QueryRecord) -> None: ...

    async def add_feedback(self, query_id: uuid.UUID, rating: str, note: str | None) -> bool: ...


class SqlQueryStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def corpus_version(self) -> int:
        async with self._session_factory() as session:
            return int(await session.scalar(select(CorpusState.version)) or 0)

    async def save(self, record: QueryRecord) -> None:
        async with self._session_factory() as session, session.begin():
            session.add(QueryLog(**record.model_dump()))

    async def add_feedback(self, query_id: uuid.UUID, rating: str, note: str | None) -> bool:
        """Latest feedback wins; False when the query was never logged."""
        async with self._session_factory() as session, session.begin():
            if await session.get(QueryLog, query_id) is None:
                return False
            statement = insert(Feedback).values(
                id=uuid.uuid4(), query_id=query_id, rating=rating, note=note
            )
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=[Feedback.query_id],
                    set_={"rating": rating, "note": note, "updated_at": func.now()},
                )
            )
        return True
