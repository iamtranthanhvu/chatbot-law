"""Builds the real clients and pipeline from settings; shared by the API and the CLI."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lawqa.api.deps import AppContainer, ReadinessCheck
from lawqa.core.config import Settings
from lawqa.db.session import create_engine, create_session_factory
from lawqa.generation.llm_client import LLMClient
from lawqa.retrieval.citation_lookup import CitationAwareRetriever, CitationLookup
from lawqa.retrieval.encoder_client import EncoderClient
from lawqa.retrieval.hybrid import HybridRetriever, RetrievalSettings
from lawqa.retrieval.rerank import Reranker, RerankingRetriever, RerankSettings
from lawqa.understanding.synonyms import (
    DEFAULT_SYNONYMS,
    SynonymDictionary,
    SynonymExpandingRetriever,
)

READINESS_HTTP_TIMEOUT = 2.0


def build_llm(settings: Settings) -> LLMClient:
    return LLMClient(
        settings.llm_base_url,
        settings.llm_model,
        settings.llm_api_key,
        api_style=settings.llm_api_style,
        num_ctx=settings.llm_num_ctx,
    )


def build_retriever(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    qdrant: AsyncQdrantClient,
    encoder: EncoderClient,
) -> CitationAwareRetriever:
    first_stage = HybridRetriever(
        qdrant, encoder, RetrievalSettings(collection=settings.qdrant_collection)
    )
    reranking = RerankingRetriever(
        first_stage,
        Reranker(
            encoder,
            RerankSettings(top_n=settings.rerank_top_n, candidates=settings.rerank_candidates),
        ),
        default_mode=settings.retrieval_mode,
    )
    expanding = SynonymExpandingRetriever(
        reranking, SynonymDictionary.load(DEFAULT_SYNONYMS), enabled=settings.synonym_expansion
    )
    return CitationAwareRetriever(
        expanding, CitationLookup(session_factory), enabled=settings.citation_lookup
    )


def llm_health_url(settings: Settings) -> str:
    base = settings.llm_base_url.rstrip("/")
    if settings.llm_api_style == "ollama":
        return f"{base.removesuffix('/v1')}/api/tags"
    return f"{base}/models"


def database_check(session_factory: async_sessionmaker[AsyncSession]) -> ReadinessCheck:
    async def check() -> None:
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))

    return check


def http_check(url: str) -> ReadinessCheck:
    async def check() -> None:
        async with httpx.AsyncClient(timeout=READINESS_HTTP_TIMEOUT) as client:
            (await client.get(url)).raise_for_status()

    return check


def qdrant_check(qdrant: AsyncQdrantClient, collection: str) -> ReadinessCheck:
    async def check() -> None:
        if not await qdrant.collection_exists(collection):
            raise LookupError(f"collection {collection} is missing")

    return check


def redis_check(redis: Redis) -> ReadinessCheck:
    async def check() -> None:
        await redis.ping()

    return check


@asynccontextmanager
async def build_container(settings: Settings) -> AsyncIterator[AppContainer]:
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    qdrant = AsyncQdrantClient(url=settings.qdrant_url)
    redis = Redis.from_url(settings.redis_url)
    try:
        yield AppContainer(
            session_factory=session_factory,
            checks={
                "database": database_check(session_factory),
                "qdrant": qdrant_check(qdrant, settings.qdrant_collection),
                "redis": redis_check(redis),
                "model_server": http_check(f"{settings.model_server_url.rstrip('/')}/healthz"),
                "llm": http_check(llm_health_url(settings)),
            },
        )
    finally:
        await redis.aclose()
        await qdrant.close()
        await engine.dispose()
