from typing import Protocol

import httpx


class EncoderError(RuntimeError):
    pass


class EncoderUnavailableError(EncoderError):
    pass


class DenseEncoder(Protocol):
    async def embed_dense(self, texts: list[str]) -> list[list[float]]: ...


class EncoderClient:
    """HTTP client for the model-server (embedding; rerank is added with the reranker)."""

    def __init__(
        self,
        base_url: str,
        *,
        batch_size: int = 32,
        timeout: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._batch_size = batch_size
        self._client = httpx.AsyncClient(
            base_url=self._base_url, timeout=timeout, transport=transport
        )

    async def embed_dense(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            body = await self._post("/embed", {"texts": texts[start : start + self._batch_size]})
            vectors.extend(body["vectors"])
        return vectors

    async def _post(self, path: str, payload: dict[str, object]) -> dict[str, list[list[float]]]:
        try:
            response = await self._client.post(path, json=payload)
        except httpx.TransportError as error:
            raise EncoderUnavailableError(
                f"Không kết nối được model-server tại {self._base_url} ({error}). "
                "Chạy `make dev-models` rồi thử lại."
            ) from error
        if response.status_code != 200:
            raise EncoderError(
                f"model-server trả lỗi {response.status_code} cho {path}: {response.text[:200]}"
            )
        result: dict[str, list[list[float]]] = response.json()
        return result

    async def aclose(self) -> None:
        await self._client.aclose()
