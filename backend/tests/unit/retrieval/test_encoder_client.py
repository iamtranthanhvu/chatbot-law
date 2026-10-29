import json

import httpx
import pytest

from lawqa.retrieval.encoder_client import EncoderClient, EncoderError, EncoderUnavailableError


def _echo_embedder(calls: list[int]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        texts = json.loads(request.content)["texts"]
        calls.append(len(texts))
        vectors = [[float(text.split()[-1]), 0.0] for text in texts]
        return httpx.Response(200, json={"vectors": vectors, "dimension": 2, "model": "fake"})

    return httpx.MockTransport(handler)


async def test_embeds_in_batches_and_keeps_order() -> None:
    calls: list[int] = []
    client = EncoderClient("http://ms", batch_size=32, transport=_echo_embedder(calls))

    vectors = await client.embed_dense([f"câu {i}" for i in range(70)])

    assert calls == [32, 32, 6]
    assert [v[0] for v in vectors] == [float(i) for i in range(70)]


async def test_empty_input_makes_no_request() -> None:
    calls: list[int] = []
    client = EncoderClient("http://ms", transport=_echo_embedder(calls))

    assert await client.embed_dense([]) == []
    assert calls == []


async def test_unreachable_model_server_is_a_clear_error() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = EncoderClient("http://127.0.0.1:8001", transport=httpx.MockTransport(refuse))

    with pytest.raises(EncoderUnavailableError, match=r"127\.0\.0\.1:8001"):
        await client.embed_dense(["đất"])


async def test_error_status_is_reported() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": "'texts[0]' is blank"})

    client = EncoderClient("http://ms", transport=httpx.MockTransport(fail))

    with pytest.raises(EncoderError, match="422"):
        await client.embed_dense(["đất"])


async def test_rerank_scores_passages_in_batches_and_keeps_order() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(len(body["passages"]))
        scores = [float(p.split()[-1]) / 100 for p in body["passages"]]
        return httpx.Response(200, json={"scores": scores, "model": "fake"})

    client = EncoderClient("http://ms", batch_size=32, transport=httpx.MockTransport(handler))

    scores = await client.rerank("thu hồi đất", [f"đoạn {i}" for i in range(40)])

    assert calls == [32, 8]
    assert scores == [i / 100 for i in range(40)]
