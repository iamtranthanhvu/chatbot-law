from typing import Protocol

import numpy as np

from model_server.config import Settings


class Embedder(Protocol):
    dimension: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class Reranker(Protocol):
    def score(self, query: str, passages: list[str]) -> list[float]: ...


def _use_fp16(settings: Settings, device: str) -> bool:
    return settings.use_fp16 if settings.use_fp16 is not None else device != "cpu"


class BGEM3Embedder:
    dimension = 1024

    def __init__(self, settings: Settings, device: str) -> None:
        from FlagEmbedding import BGEM3FlagModel

        self._settings = settings
        self._model = BGEM3FlagModel(
            settings.embed_model,
            use_fp16=_use_fp16(settings, device),
            devices=device,
            normalize_embeddings=True,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        output = self._model.encode(
            texts,
            batch_size=self._settings.max_batch_size,
            max_length=self._settings.embed_max_length,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        vectors: list[list[float]] = np.asarray(output["dense_vecs"], dtype=np.float32).tolist()
        return vectors


class BGEReranker:
    def __init__(self, settings: Settings, device: str) -> None:
        from FlagEmbedding import FlagReranker

        self._model = FlagReranker(
            settings.rerank_model,
            use_fp16=_use_fp16(settings, device),
            devices=device,
            max_length=settings.rerank_max_length,
        )

    def score(self, query: str, passages: list[str]) -> list[float]:
        scores = self._model.compute_score([(query, p) for p in passages], normalize=True)
        values = scores if isinstance(scores, list) else [scores]
        return [float(value) for value in values]
