import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lawqa.api.deps import AppContainer
from lawqa.db.models import Feedback, QueryLog
from lawqa.db.queries import SqlQueryStore
from lawqa.main import create_app
from tests.unit.api.test_ask import FakePipeline, parse_sse

pytestmark = pytest.mark.integration


@pytest.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[httpx.AsyncClient]:
    container = AppContainer(
        session_factory=session_factory,
        pipeline=FakePipeline(),
        query_store=SqlQueryStore(session_factory),
        ip_hash_secret="bí mật",
        config_hash="cfg123",
        git_sha="abc1234",
    )
    transport = httpx.ASGITransport(app=create_app(container), client=("203.0.113.9", 5000))
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as http:
        yield http


async def _ask(client: httpx.AsyncClient) -> str:
    response = await client.post("/api/v1/ask", json={"question": "Tôi có được cấp sổ đỏ?"})
    assert response.status_code == 200
    query_id: str = parse_sse(response.text)[0][1]["query_id"]
    return query_id


async def test_each_answer_is_logged_with_every_field_and_no_raw_ip(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    query_id = await _ask(client)

    async with session_factory() as session:
        row = await session.get(QueryLog, uuid.UUID(query_id))
        columns = await session.run_sync(
            lambda sync: {c["name"] for c in inspect(sync.connection()).get_columns("queries")}
        )
    assert row is not None
    assert row.outcome == "done"
    assert row.intent == "situation"
    assert row.legal_query == "cấp giấy chứng nhận"
    assert row.answer == "Được cấp [1]."
    assert row.citations == [1]
    assert row.sources[0]["chunk_ids"] == ["c-100", "c-100b"]
    assert row.missing_facts == ["Đất có tranh chấp không"]
    assert row.latency_ms == {"total": 5}
    assert row.git_sha == "abc1234" and row.config_hash == "cfg123"
    assert row.corpus_version == 0
    assert len(row.ip_hash) == 64
    assert not any(c == "ip" or c.endswith("_ip") for c in columns)
    values = " ".join(str(getattr(row, c)) for c in columns)
    assert "203.0.113.9" not in values


async def test_feedback_is_stored_and_the_latest_wins(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    query_id = await _ask(client)

    first = await client.post(f"/api/v1/queries/{query_id}/feedback", json={"rating": "up"})
    second = await client.post(
        f"/api/v1/queries/{query_id}/feedback", json={"rating": "down", "note": "thiếu căn cứ"}
    )

    assert first.status_code == second.status_code == 200
    async with session_factory() as session:
        rows = (await session.scalars(select(Feedback))).all()
    assert [(r.rating, r.note) for r in rows] == [("down", "thiếu căn cứ")]


async def test_feedback_for_an_unknown_query_is_404(client: httpx.AsyncClient) -> None:
    response = await client.post(f"/api/v1/queries/{uuid.uuid4()}/feedback", json={"rating": "up"})

    assert response.status_code == 404
