import pytest
from pydantic import ValidationError

from lawqa.core.config import Settings

REQUIRED = {
    "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
    "QDRANT_URL": "http://localhost:6333",
    "REDIS_URL": "redis://localhost:6379/0",
    "MODEL_SERVER_URL": "http://localhost:8001",
    "LLM_BASE_URL": "http://localhost:11434/v1",
    "LLM_MODEL": "qwen3:8b",
}


def test_reads_values_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in REQUIRED.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CHUNK_MAX_TOKENS", "384")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.llm_model == "qwen3:8b"
    assert settings.chunk_max_tokens == 384
    assert settings.qdrant_collection == "lawqa_chunks"


def test_missing_required_variable_names_the_field(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in REQUIRED.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("DATABASE_URL")

    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)  # type: ignore[call-arg]
