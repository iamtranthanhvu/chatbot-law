import asyncio
import threading
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from model_server.backends import BGEM3Embedder, BGEReranker, Embedder, Reranker
from model_server.config import Settings
from model_server.devices import resolve_device


class EmbedRequest(BaseModel):
    texts: list[str]


class EmbedResponse(BaseModel):
    vectors: list[list[float]]
    dimension: int
    model: str


class RerankRequest(BaseModel):
    query: str
    passages: list[str]


class RerankResponse(BaseModel):
    scores: list[float]
    model: str


class HealthResponse(BaseModel):
    status: str
    device: str
    embed_model: str
    rerank_model: str
    embed_loaded: bool
    rerank_loaded: bool


class _LazyModel[T]:
    """Loads a model on first use."""

    def __init__(self, factory: Callable[[], T]) -> None:
        self._factory = factory
        self._instance: T | None = None
        self._load_lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self._instance is not None

    def get(self) -> T:
        with self._load_lock:
            if self._instance is None:
                self._instance = self._factory()
            return self._instance


def create_app(
    settings: Settings | None = None,
    *,
    embedder_factory: Callable[[], Embedder] | None = None,
    reranker_factory: Callable[[], Reranker] | None = None,
) -> FastAPI:
    settings = settings or Settings()
    device = resolve_device(settings.device)
    embedder = _LazyModel(embedder_factory or (lambda: BGEM3Embedder(settings, device)))
    reranker = _LazyModel(reranker_factory or (lambda: BGEReranker(settings, device)))
    # One lock for the whole device: MPS aborts the process ("A command encoder is already
    # encoding to this command buffer") when two models submit work from different threads.
    device_lock = asyncio.Lock()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await asyncio.to_thread(embedder.get)
        yield

    app = FastAPI(title="Law QA model server", lifespan=lifespan)

    def validate_texts(texts: list[str], field: str) -> None:
        if not texts:
            raise HTTPException(422, f"'{field}' must not be empty")
        if len(texts) > settings.max_batch_size:
            raise HTTPException(422, f"'{field}' exceeds {settings.max_batch_size} items")
        for i, text in enumerate(texts):
            if not text.strip():
                raise HTTPException(422, f"'{field}[{i}]' is blank")
            if len(text) > settings.max_text_chars:
                raise HTTPException(422, f"'{field}[{i}]' exceeds {settings.max_text_chars} chars")

    @app.post("/embed")
    async def embed(request: EmbedRequest) -> EmbedResponse:
        validate_texts(request.texts, "texts")
        model = await asyncio.to_thread(embedder.get)
        async with device_lock:
            raw = await asyncio.to_thread(model.embed, request.texts)
        matrix = np.asarray(raw, dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        normalized = matrix / np.where(norms == 0, 1.0, norms)
        return EmbedResponse(
            vectors=normalized.tolist(), dimension=model.dimension, model=settings.embed_model
        )

    @app.post("/rerank")
    async def rerank(request: RerankRequest) -> RerankResponse:
        validate_texts([request.query], "query")
        validate_texts(request.passages, "passages")
        model = await asyncio.to_thread(reranker.get)
        async with device_lock:
            scores = await asyncio.to_thread(model.score, request.query, request.passages)
        return RerankResponse(scores=scores, model=settings.rerank_model)

    @app.get("/healthz")
    async def healthz() -> HealthResponse:
        return HealthResponse(
            status="ok",
            device=device,
            embed_model=settings.embed_model,
            rerank_model=settings.rerank_model,
            embed_loaded=embedder.loaded,
            rerank_loaded=reranker.loaded,
        )

    return app


def app_factory() -> FastAPI:
    return create_app()
