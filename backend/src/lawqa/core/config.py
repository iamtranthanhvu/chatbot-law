from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV = SettingsConfigDict(env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore")


class IngestionSettings(BaseSettings):
    """Settings needed to parse and chunk documents; no infrastructure required."""

    model_config = _ENV

    chunk_max_tokens: int = Field(default=512, gt=64)
    tokenizer_name: str = "BAAI/bge-m3"


class DatabaseSettings(BaseSettings):
    model_config = _ENV

    database_url: str


class Settings(IngestionSettings, DatabaseSettings):
    model_config = _ENV

    qdrant_url: str
    qdrant_collection: str = "lawqa_chunks"
    redis_url: str
    model_server_url: str

    llm_base_url: str
    llm_api_key: str = "not-needed"
    llm_model: str
    llm_api_style: Literal["openai", "ollama"] = "openai"
    llm_num_ctx: int = Field(default=8192, gt=0)

    judge_base_url: str | None = None
    judge_model: str | None = None
    judge_api_key: str = "not-needed"
    judge_api_style: Literal["openai", "ollama"] = "openai"

    retrieval_mode: str = "hybrid+rerank"
    rerank_top_n: int = Field(default=8, gt=0)
    rerank_candidates: int = Field(default=40, gt=0)
    rerank_min_score: float = Field(default=0.005, ge=0, le=1)

    context_max_tokens: int = Field(default=6000, gt=0)
    max_answer_tokens: int = Field(default=1024, gt=0)
    max_context_chunks: int = Field(default=8, gt=0)

    log_level: str = "INFO"
    log_json: bool = False

    @model_validator(mode="after")
    def _context_fits_ollama_window(self) -> Self:
        # Ollama silently drops the start of a prompt longer than num_ctx — the system rules
        # go first. 1024 tokens cover the system prompt, question and source headers.
        needed = self.context_max_tokens + self.max_answer_tokens + 1024
        if self.llm_api_style == "ollama" and needed > self.llm_num_ctx:
            raise ValueError(
                f"LLM_NUM_CTX={self.llm_num_ctx} nhỏ hơn mức cần {needed} "
                "(CONTEXT_MAX_TOKENS + MAX_ANSWER_TOKENS + 1024)"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
