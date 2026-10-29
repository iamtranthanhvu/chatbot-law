from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MS_", env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    embed_model: str = "BAAI/bge-m3"
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    device: str = "auto"
    use_fp16: bool | None = None  # None: fp16 on GPU (cuda/mps), fp32 on cpu

    max_batch_size: int = Field(default=64, gt=0)
    max_text_chars: int = Field(default=8000, gt=0)
    embed_max_length: int = Field(default=1024, gt=0)
    rerank_max_length: int = Field(default=1024, gt=0)
