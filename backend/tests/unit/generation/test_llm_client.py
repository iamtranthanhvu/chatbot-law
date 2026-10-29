import json
from collections.abc import Callable

import httpx
import pytest

from lawqa.generation.llm_client import LLMClient, LLMError, LLMUnavailableError

MESSAGES = [{"role": "user", "content": "Điều kiện chuyển nhượng quyền sử dụng đất?"}]


def _sse(pieces: list[str]) -> bytes:
    events = []
    for piece in pieces:
        chunk = {
            "id": "1",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "qwen3:8b",
            "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}],
        }
        events.append(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n")
    events.append("data: [DONE]\n\n")
    return "".join(events).encode()


def _client(handler: Callable[[httpx.Request], httpx.Response], **kwargs: object) -> LLMClient:
    return LLMClient(
        base_url="http://llm/v1",
        model="qwen3:8b",
        transport=httpx.MockTransport(handler),
        retry_backoff=0.0,
        **kwargs,  # type: ignore[arg-type]
    )


async def _collect(client: LLMClient) -> str:
    return "".join([piece async for piece in client.stream(MESSAGES)])


async def test_streams_content_pieces() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_sse(["Người ", "sử dụng ", "đất."]))

    assert await _collect(_client(handler)) == "Người sử dụng đất."


async def test_think_blocks_are_removed_even_when_split_across_chunks() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        pieces = ["<thi", "nk>suy nghĩ nội", " bộ</th", "ink>\n\nKết luận", ": được phép."]
        return httpx.Response(200, content=_sse(pieces))

    assert await _collect(_client(handler)) == "Kết luận: được phép."


async def test_request_asks_for_low_temperature_and_no_thinking() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, content=_sse(["ok"]))

    await _collect(_client(handler))

    body = seen[0]
    assert body["model"] == "qwen3:8b"
    assert body["stream"] is True
    assert body["temperature"] == 0.1
    assert body["chat_template_kwargs"] == {"enable_thinking": False}


async def test_retries_transient_failures_before_streaming() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503, json={"error": "loading model"})
        return httpx.Response(200, content=_sse(["ok"]))

    assert await _collect(_client(handler, max_retries=2)) == "ok"
    assert attempts == 3


async def test_unreachable_server_raises_after_retries() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(LLMUnavailableError, match="http://llm/v1"):
        await _collect(_client(handler, max_retries=2))
    assert attempts == 3


async def test_client_errors_are_not_retried() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(400, json={"error": {"message": "bad request"}})

    with pytest.raises(LLMError):
        await _collect(_client(handler, max_retries=2))
    assert attempts == 1


async def test_complete_returns_full_text_without_think_block() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = {
            "id": "1",
            "object": "chat.completion",
            "created": 0,
            "model": "qwen3:8b",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": '<think>x</think>{"intent": "lookup"}',
                    },
                    "finish_reason": "stop",
                }
            ],
        }
        return httpx.Response(200, json=body)

    assert await _client(handler).complete(MESSAGES) == '{"intent": "lookup"}'


def _ndjson(pieces: list[str], thinking: str = "") -> bytes:
    lines = []
    if thinking:
        message = {"role": "assistant", "content": "", "thinking": thinking}
        lines.append({"message": message, "done": False})
    lines += [{"message": {"role": "assistant", "content": p}, "done": False} for p in pieces]
    lines.append({"message": {"role": "assistant", "content": ""}, "done": True, "eval_count": 3})
    return "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines).encode()


def _ollama(handler: Callable[[httpx.Request], httpx.Response], **kwargs: object) -> LLMClient:
    return LLMClient(
        base_url="http://ollama:11434/v1",
        model="qwen3:8b",
        api_style="ollama",
        transport=httpx.MockTransport(handler),
        retry_backoff=0.0,
        **kwargs,  # type: ignore[arg-type]
    )


async def test_ollama_style_streams_ndjson_and_ignores_thinking() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_ndjson(["Đất đai ", "thuộc sở hữu toàn dân."], "nghĩ"))

    pieces = [piece async for piece in _ollama(handler).stream(MESSAGES)]

    assert "".join(pieces) == "Đất đai thuộc sở hữu toàn dân."


async def test_ollama_style_uses_native_chat_with_thinking_off() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=_ndjson(["ok"]))

    _ = [piece async for piece in _ollama(handler).stream(MESSAGES, max_tokens=64)]

    request = seen[0]
    body = json.loads(request.content)
    assert request.url.path == "/api/chat"
    assert body["think"] is False
    assert body["stream"] is True
    assert body["options"] == {"temperature": 0.1, "num_predict": 64}
    assert "chat_template_kwargs" not in body


async def test_ollama_style_complete_maps_json_schema_to_format() -> None:
    seen: list[dict[str, object]] = []
    schema = {"type": "object", "properties": {"intent": {"type": "string"}}}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": '{"intent": "lookup"}'},
                "done": True,
            },
        )

    result = await _ollama(handler).complete(
        MESSAGES, response_format={"type": "json_schema", "json_schema": {"schema": schema}}
    )

    assert result == '{"intent": "lookup"}'
    assert seen[0]["format"] == schema
    assert seen[0]["stream"] is False


async def test_ollama_style_reports_errors_from_the_stream() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b'{"error": "model \'qwen3:8b\' not found"}\n')

    with pytest.raises(LLMError, match="not found"):
        _ = [piece async for piece in _ollama(handler).stream(MESSAGES)]


async def test_ollama_style_sends_context_window_size() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, content=_ndjson(["ok"]))

    _ = [piece async for piece in _ollama(handler, num_ctx=8192).stream(MESSAGES)]

    options = seen[0]["options"]
    assert isinstance(options, dict) and options["num_ctx"] == 8192
