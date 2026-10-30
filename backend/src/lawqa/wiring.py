"""Builds the real clients and pipeline from settings; shared by the API and the CLI."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lawqa.api.concurrency import GenerationSlots
from lawqa.api.deps import AppContainer, ReadinessCheck
from lawqa.core.cache import AnswerCache
from lawqa.core.config import Settings
from lawqa.core.rate_limit import RateLimit, RateLimiter
from lawqa.db.queries import SqlQueryStore
from lawqa.db.session import create_engine, create_session_factory
from lawqa.eval.runner import config_hash, git_sha
from lawqa.generation.llm_client import LLMClient
from lawqa.ingestion.tokens import HFTokenCounter
from lawqa.pipelines.hybrid import HybridRAGPipeline, PipelineSettings, Retriever
from lawqa.retrieval.citation_lookup import CitationAwareRetriever, CitationLookup
from lawqa.retrieval.encoder_client import EncoderClient
from lawqa.retrieval.hybrid import HybridRetriever, RetrievalSettings
from lawqa.retrieval.rerank import Reranker, RerankingRetriever, RerankSettings
from lawqa.understanding.classifier import QueryUnderstanding
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


def build_pipeline(settings: Settings, retriever: Retriever, llm: LLMClient) -> HybridRAGPipeline:
    return HybridRAGPipeline(
        retriever=retriever,
        llm=llm,
        counter=HFTokenCounter(settings.tokenizer_name),
        settings=PipelineSettings(
            context_max_tokens=settings.context_max_tokens,
            max_answer_tokens=settings.max_answer_tokens,
            max_chunks=settings.max_context_chunks,
            min_rerank_score=settings.rerank_min_score,
            out_of_scope_override_score=settings.out_of_scope_override_score,
            search_with_legal_query=settings.search_with_legal_query,
        ),
        understanding=QueryUnderstanding(llm) if settings.query_understanding else None,
    )


def answer_config(settings: Settings) -> dict[str, object]:
    """Settings that change answers; hashed into query logs, eval reports and cache keys."""
    return {
        "llm_model": settings.llm_model,
        "context_max_tokens": settings.context_max_tokens,
        "max_context_chunks": settings.max_context_chunks,
        "max_answer_tokens": settings.max_answer_tokens,
        "retrieval_mode": settings.retrieval_mode,
        "rerank_top_n": settings.rerank_top_n,
        "rerank_candidates": settings.rerank_candidates,
        "rerank_min_score": settings.rerank_min_score,
        "citation_lookup": settings.citation_lookup,
        "synonym_expansion": settings.synonym_expansion,
        "query_understanding": settings.query_understanding,
        "search_with_legal_query": settings.search_with_legal_query,
        "out_of_scope_override_score": settings.out_of_scope_override_score,
        "retrieval": RetrievalSettings(collection=settings.qdrant_collection).model_dump(),
    }


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
    if settings.ip_hash_secret is None:
        raise RuntimeError("IP_HASH_SECRET chưa được đặt (cần để băm IP trong log truy vấn)")
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    qdrant = AsyncQdrantClient(url=settings.qdrant_url)
    redis = Redis.from_url(settings.redis_url)
    encoder = EncoderClient(settings.model_server_url)
    llm = build_llm(settings)
    retriever = build_retriever(settings, session_factory, qdrant, encoder)
    try:
        yield AppContainer(
            session_factory=session_factory,
            pipeline=build_pipeline(settings, retriever, llm),
            query_store=SqlQueryStore(session_factory),
            ip_hash_secret=settings.ip_hash_secret.get_secret_value(),
            config_hash=config_hash(answer_config(settings)),
            git_sha=settings.git_sha or git_sha(),
            rate_limiter=RateLimiter(
                redis,
                (
                    RateLimit(settings.rate_limit_per_minute, 60),
                    RateLimit(settings.rate_limit_per_day, 86400),
                ),
            ),
            answer_cache=(
                AnswerCache(redis, settings.answer_cache_ttl_seconds)
                if settings.answer_cache_ttl_seconds
                else None
            ),
            slots=GenerationSlots(
                settings.max_concurrent_generations, settings.generation_wait_seconds
            ),
            checks={
                "database": database_check(session_factory),
                "qdrant": qdrant_check(qdrant, settings.qdrant_collection),
                "redis": redis_check(redis),
                "model_server": http_check(f"{settings.model_server_url.rstrip('/')}/healthz"),
                "llm": http_check(llm_health_url(settings)),
            },
        )
    finally:
        await llm.aclose()
        await encoder.aclose()
        await redis.aclose()
        await qdrant.close()
        await engine.dispose()
