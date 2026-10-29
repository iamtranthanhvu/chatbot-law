import math

import pytest
from fastapi.testclient import TestClient

from model_server.main import create_app

pytestmark = pytest.mark.models

SENTENCES = [
    f"Câu {i}: hộ gia đình, cá nhân sử dụng đất ổn định được cấp giấy chứng nhận."
    for i in range(32)
]


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(create_app()) as test_client:
        yield test_client


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_uses_gpu_when_available(client: TestClient) -> None:
    import torch

    expected = (
        "cuda"
        if torch.cuda.is_available()
        else "mps"
        if torch.backends.mps.is_available()
        else "cpu"
    )
    assert client.get("/healthz").json()["device"] == expected


def test_embeds_a_batch_into_normalized_1024d_vectors(client: TestClient) -> None:
    body = client.post("/embed", json={"texts": SENTENCES}).json()

    assert body["dimension"] == 1024
    assert len(body["vectors"]) == 32
    assert all(len(v) == 1024 for v in body["vectors"])
    assert all(math.isclose(math.sqrt(_cosine(v, v)), 1.0, rel_tol=1e-3) for v in body["vectors"])


def test_colloquial_term_is_close_to_legal_term(client: TestClient) -> None:
    texts = ["sổ đỏ", "giấy chứng nhận quyền sử dụng đất", "thuế thu nhập cá nhân"]
    so_do, giay_chung_nhan, thue = client.post("/embed", json={"texts": texts}).json()["vectors"]

    assert _cosine(so_do, giay_chung_nhan) > _cosine(so_do, thue)


def test_reranker_prefers_the_relevant_passage(client: TestClient) -> None:
    response = client.post(
        "/rerank",
        json={
            "query": "Nhà nước thu hồi đất trong những trường hợp nào?",
            "passages": [
                "Thuế thu nhập cá nhân áp dụng đối với người có thu nhập chịu thuế.",
                "Nhà nước quyết định thu hồi đất vì mục đích quốc phòng, an ninh.",
            ],
        },
    ).json()

    unrelated, relevant = response["scores"]
    assert relevant > unrelated
    assert 0.0 <= unrelated <= 1.0 and 0.0 <= relevant <= 1.0
