import math

import pytest
from fastapi.testclient import TestClient

from model_server.config import Settings
from model_server.devices import resolve_device
from model_server.main import create_app


class FakeEmbedder:
    dimension = 4

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 1.0, 0.0, 2.0] for text in texts]


class FakeReranker:
    loads = 0

    def __init__(self) -> None:
        FakeReranker.loads += 1

    def score(self, query: str, passages: list[str]) -> list[float]:
        return [1.0 if query in passage else 0.1 for passage in passages]


@pytest.fixture
def client() -> TestClient:
    FakeReranker.loads = 0
    settings = Settings(device="cpu", max_batch_size=8, max_text_chars=200)
    app = create_app(settings, embedder_factory=FakeEmbedder, reranker_factory=FakeReranker)
    return TestClient(app)


def test_embed_returns_l2_normalized_vectors(client: TestClient) -> None:
    response = client.post("/embed", json={"texts": ["đất ở", "giấy chứng nhận"]})

    assert response.status_code == 200
    body = response.json()
    assert body["dimension"] == 4
    assert len(body["vectors"]) == 2
    for vector in body["vectors"]:
        assert math.isclose(math.sqrt(sum(v * v for v in vector)), 1.0, rel_tol=1e-6)


@pytest.mark.parametrize(
    "payload",
    [
        {"texts": []},
        {"texts": ["   "]},
        {"texts": ["x" * 201]},
        {"texts": ["a"] * 9},
    ],
    ids=["empty-list", "blank-text", "too-long", "batch-too-large"],
)
def test_embed_rejects_invalid_input(client: TestClient, payload: dict[str, list[str]]) -> None:
    assert client.post("/embed", json=payload).status_code == 422


def test_rerank_scores_each_passage_in_order(client: TestClient) -> None:
    response = client.post(
        "/rerank",
        json={"query": "thu hồi đất", "passages": ["không liên quan", "Nhà nước thu hồi đất"]},
    )

    assert response.status_code == 200
    assert response.json()["scores"] == [0.1, 1.0]


def test_rerank_rejects_empty_passages(client: TestClient) -> None:
    assert client.post("/rerank", json={"query": "q", "passages": []}).status_code == 422


def test_reranker_is_loaded_lazily_once(client: TestClient) -> None:
    assert client.get("/healthz").json()["rerank_loaded"] is False

    client.post("/rerank", json={"query": "q", "passages": ["q"]})
    client.post("/rerank", json={"query": "q", "passages": ["q"]})

    assert FakeReranker.loads == 1
    assert client.get("/healthz").json()["rerank_loaded"] is True


def test_healthz_reports_device_and_models(client: TestClient) -> None:
    body = client.get("/healthz").json()

    assert body["status"] == "ok"
    assert body["device"] == "cpu"
    assert body["embed_model"] == "BAAI/bge-m3"


@pytest.mark.parametrize(
    ("setting", "cuda", "mps", "expected"),
    [
        ("auto", True, True, "cuda"),
        ("auto", False, True, "mps"),
        ("auto", False, False, "cpu"),
        ("cpu", True, True, "cpu"),
    ],
)
def test_resolve_device(setting: str, cuda: bool, mps: bool, expected: str) -> None:
    assert resolve_device(setting, cuda_available=cuda, mps_available=mps) == expected
