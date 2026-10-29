import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, Literal

import httpx

ApiStyle = Literal["openai", "ollama"]

Message = dict[str, str]

_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


class LLMError(RuntimeError):
    pass


class LLMUnavailableError(LLMError):
    pass


class LLMTimeoutError(LLMError):
    pass


class ThinkFilter:
    """Removes <think>…</think> blocks from a token stream, even when tags are split
    across chunks, and drops the whitespace a reasoning model leaves before the answer."""

    OPEN = "<think>"
    CLOSE = "</think>"

    def __init__(self) -> None:
        self._buffer = ""
        self._inside = False
        self._started = False

    def feed(self, text: str) -> str:
        self._buffer += text
        visible: list[str] = []
        while True:
            if self._inside:
                end = self._buffer.find(self.CLOSE)
                if end == -1:
                    self._buffer = self._buffer[-(len(self.CLOSE) - 1) :]
                    break
                self._buffer = self._buffer[end + len(self.CLOSE) :]
                self._inside = False
                continue
            start = self._buffer.find(self.OPEN)
            if start == -1:
                keep = _partial_prefix_length(self._buffer, self.OPEN)
                visible.append(self._buffer[: len(self._buffer) - keep])
                self._buffer = self._buffer[len(self._buffer) - keep :]
                break
            visible.append(self._buffer[:start])
            self._buffer = self._buffer[start + len(self.OPEN) :]
            self._inside = True
        return self._emit("".join(visible))

    def flush(self) -> str:
        rest = "" if self._inside else self._buffer
        self._buffer = ""
        return self._emit(rest)

    def _emit(self, text: str) -> str:
        if not self._started:
            text = text.lstrip()
            self._started = bool(text)
        return text


def _partial_prefix_length(text: str, tag: str) -> int:
    for size in range(min(len(tag) - 1, len(text)), 0, -1):
        if tag.startswith(text[-size:]):
            return size
    return 0


class LLMClient:
    """Chat client for vLLM (OpenAI-compatible API, prod) and Ollama (native API, dev).

    Ollama ignores every "thinking off" switch on its /v1 endpoint, so Qwen3 keeps
    reasoning silently; only the native /api/chat honours think=false.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "not-needed",
        *,
        temperature: float = 0.1,
        timeout: float = 120.0,
        connect_timeout: float = 5.0,
        max_retries: int = 2,
        retry_backoff: float = 0.5,
        api_style: ApiStyle = "openai",
        num_ctx: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_style = api_style
        self._num_ctx = num_ctx
        base_url = base_url.rstrip("/")
        if api_style == "ollama":
            base_url = base_url.removesuffix("/v1")
        self._base_url = base_url
        self._path = "/api/chat" if api_style == "ollama" else "/chat/completions"
        self._model = model
        self._temperature = temperature
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(timeout, connect=connect_timeout),
            transport=transport,
        )

    @property
    def model(self) -> str:
        return self._model

    async def stream(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        payload = self._payload(
            messages, stream=True, temperature=temperature, max_tokens=max_tokens
        )
        response = await self._send(payload, stream=True)
        think = ThinkFilter()
        try:
            async for line in response.aiter_lines():
                piece, done = self._parse_stream_line(line)
                if visible := think.feed(piece):
                    yield visible
                if done:
                    break
            if tail := think.flush():
                yield tail
        except httpx.TimeoutException as error:
            raise LLMTimeoutError(f"LLM ngừng trả dữ liệu giữa chừng ({self._base_url})") from error
        except httpx.TransportError as error:
            raise LLMUnavailableError(f"Mất kết nối tới LLM tại {self._base_url}") from error
        finally:
            await response.aclose()

    async def complete(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        payload = self._payload(
            messages, stream=False, temperature=temperature, max_tokens=max_tokens
        )
        if response_format is not None:
            if self._api_style == "ollama":
                payload["format"] = _ollama_format(response_format)
            else:
                payload["response_format"] = response_format
        response = await self._send(payload, stream=False)
        body = response.json()
        message = body["message"] if self._api_style == "ollama" else body["choices"][0]["message"]
        content = message.get("content") or ""
        think = ThinkFilter()
        return (think.feed(content) + think.flush()).strip()

    def _payload(
        self,
        messages: list[Message],
        *,
        stream: bool,
        temperature: float | None,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        temperature = self._temperature if temperature is None else temperature
        if self._api_style == "ollama":
            options: dict[str, Any] = {"temperature": temperature}
            if max_tokens is not None:
                options["num_predict"] = max_tokens
            if self._num_ctx is not None:
                options["num_ctx"] = self._num_ctx
            return {
                "model": self._model,
                "messages": messages,
                "stream": stream,
                "think": False,
                "options": options,
            }
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": stream,
            "temperature": temperature,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        return payload

    def _parse_stream_line(self, line: str) -> tuple[str, bool]:
        """Return (content piece, stream finished) for one line of the response stream."""
        if self._api_style == "ollama":
            if not line.strip():
                return "", False
            event = json.loads(line)
            if "error" in event:
                raise LLMError(f"LLM trả lỗi: {event['error']}")
            return (event.get("message") or {}).get("content") or "", bool(event.get("done"))
        if not line.startswith("data:"):
            return "", False
        data = line.removeprefix("data:").strip()
        if data == "[DONE]":
            return "", True
        choices = json.loads(data).get("choices") or [{}]
        return (choices[0].get("delta") or {}).get("content") or "", False

    async def _send(self, payload: dict[str, Any], *, stream: bool) -> httpx.Response:
        last_error: LLMError | None = None
        for attempt in range(self._max_retries + 1):
            if attempt:
                await asyncio.sleep(self._retry_backoff * 2 ** (attempt - 1))
            request = self._client.build_request("POST", self._path, json=payload)
            try:
                response = await self._client.send(request, stream=stream)
            except httpx.TimeoutException as error:
                last_error = LLMTimeoutError(f"LLM tại {self._base_url} không phản hồi kịp")
                last_error.__cause__ = error
                continue
            except httpx.TransportError as error:
                last_error = LLMUnavailableError(
                    f"Không kết nối được LLM tại {self._base_url} ({error})"
                )
                last_error.__cause__ = error
                continue

            if response.status_code == 200:
                return response
            body = (await response.aread()).decode(errors="replace")[:300]
            await response.aclose()
            last_error = LLMError(f"LLM trả lỗi {response.status_code}: {body}")
            if response.status_code not in _RETRYABLE_STATUS:
                raise last_error
        assert last_error is not None
        raise last_error

    async def aclose(self) -> None:
        await self._client.aclose()


def _ollama_format(response_format: dict[str, Any]) -> dict[str, Any] | str:
    if response_format.get("type") == "json_schema":
        schema: dict[str, Any] = response_format["json_schema"]["schema"]
        return schema
    return "json"
