from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV = SettingsConfigDict(env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore")


class IngestionSettings(BaseSettings):
    """Settings needed to parse and chunk documents; no infrastructure required."""

    model_config = _ENV

    chunk_max_tokens: int = Field(default=512, gt=64)
    tokenizer_name: str = "BAAI/bge-m3"


class Settings(IngestionSettings):
    model_config = _ENV

    database_url: str
    qdrant_url: str
    qdrant_collection: str = "lawqa_chunks"
    redis_url: str
    model_server_url: str

    llm_base_url: str
    llm_api_key: str = "not-needed"
    llm_model: str

    log_level: str = "INFO"
    log_json: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
