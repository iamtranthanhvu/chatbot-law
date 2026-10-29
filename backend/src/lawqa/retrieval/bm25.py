from collections import Counter
from dataclasses import dataclass
from statistics import fmean

import mmh3
from pydantic import BaseModel, ConfigDict, Field

from lawqa.retrieval.bm25_tokenizer import tokenize


class BM25Params(BaseModel):
    model_config = ConfigDict(frozen=True)

    k1: float = 1.2
    b: float = 0.75
    avgdl: float = Field(gt=0)


@dataclass(frozen=True)
class SparseVector:
    indices: list[int]
    values: list[float]


def token_id(token: str) -> int:
    return mmh3.hash(token, signed=False)


def encode_document(text: str, params: BM25Params) -> SparseVector:
    """BM25 term-frequency part; Qdrant's `modifier: idf` multiplies in the IDF at query time.

    weight = tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl / avgdl))
    """
    tokens = tokenize(text)
    counts = Counter(token_id(token) for token in tokens)
    length_norm = params.k1 * (1 - params.b + params.b * len(tokens) / params.avgdl)
    weights = {index: tf * (params.k1 + 1) / (tf + length_norm) for index, tf in counts.items()}
    indices = sorted(weights)
    return SparseVector(indices=indices, values=[weights[i] for i in indices])


def encode_query(text: str) -> SparseVector:
    indices = sorted({token_id(token) for token in tokenize(text)})
    return SparseVector(indices=indices, values=[1.0] * len(indices))


def average_length(texts: list[str]) -> float:
    return fmean(len(tokenize(text)) for text in texts)
