import time

import pytest

from lawqa.core.config import get_settings
from lawqa.generation.llm_client import LLMClient

pytestmark = pytest.mark.llm


async def test_real_llm_streams_vietnamese_without_thinking() -> None:
    settings = get_settings()
    client = LLMClient(
        settings.llm_base_url,
        settings.llm_model,
        settings.llm_api_key,
        api_style=settings.llm_api_style,
    )
    messages = [
        {"role": "system", "content": "Trả lời ngắn gọn bằng tiếng Việt."},
        {"role": "user", "content": "Đất đai thuộc sở hữu của ai theo pháp luật Việt Nam?"},
    ]

    started = time.monotonic()
    pieces: list[str] = []
    first_token_at: float | None = None
    async for piece in client.stream(messages, max_tokens=200):
        first_token_at = first_token_at or time.monotonic()
        pieces.append(piece)
    await client.aclose()

    answer = "".join(pieces)
    print(
        f"\nmodel={settings.llm_model} ttft={(first_token_at or started) - started:.2f}s "
        f"total={time.monotonic() - started:.2f}s pieces={len(pieces)}\n{answer}"
    )
    assert len(pieces) > 1
    assert "<think>" not in answer and "</think>" not in answer
    assert answer.strip()
