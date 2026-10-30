from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lawqa.api.concurrency import GenerationSlots
from lawqa.core.cache import AnswerCache
from lawqa.core.rate_limit import RateLimiter
from lawqa.db.queries import QueryStore
from lawqa.pipelines.base import PipelineEvent, Query

ReadinessCheck = Callable[[], Awaitable[None]]


class AnsweringPipeline(Protocol):
    name: str

    def answer(self, query: Query) -> AsyncIterator[PipelineEvent]: ...


@dataclass
class AppContainer:
    """Everything the routes need, built once at startup (or by a test with fakes)."""

    checks: dict[str, ReadinessCheck] = field(default_factory=dict)
    session_factory: async_sessionmaker[AsyncSession] | None = None
    pipeline: AnsweringPipeline | None = None
    query_store: QueryStore | None = None
    ip_hash_secret: str = ""
    config_hash: str = ""
    git_sha: str = ""
    # Each protection is off when missing (tests, or a deliberate opt-out).
    rate_limiter: RateLimiter | None = None
    answer_cache: AnswerCache | None = None
    slots: GenerationSlots | None = None


def get_container(request: Request) -> AppContainer:
    container: AppContainer = request.app.state.container
    return container


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    factory = get_container(request).session_factory
    if factory is None:
        raise RuntimeError("database is not configured")
    return factory


def get_pipeline(request: Request) -> AnsweringPipeline:
    pipeline = get_container(request).pipeline
    if pipeline is None:
        raise RuntimeError("pipeline is not configured")
    return pipeline


def get_query_store(request: Request) -> QueryStore:
    store = get_container(request).query_store
    if store is None:
        raise RuntimeError("query store is not configured")
    return store
