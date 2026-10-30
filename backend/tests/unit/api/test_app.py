import io
import json
from collections.abc import AsyncIterator

import httpx
import pytest

from lawqa.api.deps import AppContainer
from lawqa.core.logging import configure_logging
from lawqa.main import create_app


async def ok() -> None:
    return None


async def down() -> None:
    raise ConnectionError("connection refused")


def _container(**checks: object) -> AppContainer:
    return AppContainer(checks=checks or {"database": ok})  # type: ignore[arg-type]


@pytest.fixture
def log_stream() -> io.StringIO:
    stream = io.StringIO()
    configure_logging("INFO", json_output=True, stream=stream)
    return stream


async def _client(container: AppContainer) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_app(container))
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
        yield client


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async for c in _client(_container(database=ok, qdrant=ok)):
        yield c


async def test_healthz_is_always_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readyz_lists_every_component(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok", "qdrant": "ok"}}


async def test_readyz_is_503_and_names_the_failing_component() -> None:
    async for client in _client(_container(database=ok, qdrant=down)):
        response = await client.get("/api/v1/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["qdrant"].startswith("error: ConnectionError")


async def test_every_request_log_carries_the_request_id(
    client: httpx.AsyncClient, log_stream: io.StringIO
) -> None:
    response = await client.get("/api/v1/healthz")

    request_id = response.headers["x-request-id"]
    records = [json.loads(line) for line in log_stream.getvalue().splitlines()]
    access = [r for r in records if r.get("event") == "request"]
    assert access and all(r["request_id"] == request_id for r in access)
    assert access[0]["status"] == 200


async def test_a_client_supplied_request_id_is_kept(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/healthz", headers={"x-request-id": "abc-123"})

    assert response.headers["x-request-id"] == "abc-123"


async def test_unknown_routes_use_the_error_shape(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/khong-co")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
