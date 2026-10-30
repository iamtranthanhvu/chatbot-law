from collections.abc import AsyncIterator
from datetime import date

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lawqa.api.deps import AppContainer
from lawqa.ingestion.chunker import chunk_document
from lawqa.ingestion.legal_parser import parse_body
from lawqa.ingestion.metadata import DocumentMetadata
from lawqa.ingestion.models import ParsedDocument
from lawqa.ingestion.store import chunk_uuid, document_uuid, save_document
from lawqa.main import create_app
from lawqa.wiring import database_check, http_check
from tests.unit.pipelines.conftest import WordCounter

pytestmark = pytest.mark.integration

SO_HIEU = "45/2013/QH13"


def _document() -> ParsedDocument:
    return ParsedDocument(
        metadata=DocumentMetadata(
            so_hieu=SO_HIEU,
            doc_type="Luật",
            title="Luật Đất đai",
            name="Luật Đất đai",
            issuer="Quốc hội",
            passed_date=date(2013, 11, 29),
            effective_date=date(2014, 7, 1),
        ),
        preamble=[],
        structure=parse_body(
            [
                "Chương VII",
                "ĐĂNG KÝ ĐẤT ĐAI",
                "Điều 100. Cấp Giấy chứng nhận cho hộ gia đình, cá nhân",
                "1. Hộ gia đình, cá nhân đang sử dụng đất ổn định thì được cấp Giấy chứng nhận.",
                "2. Hộ gia đình, cá nhân được sử dụng đất theo bản án thì được cấp.",
            ]
        ),
        sha256="b" * 64,
        source_file="Luật-45-2013-QH13.docx",
    )


@pytest.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession], postgres_url: str
) -> AsyncIterator[httpx.AsyncClient]:
    document = _document()
    await save_document(session_factory, document, chunk_document(document, WordCounter(), 512))
    container = AppContainer(
        session_factory=session_factory,
        checks={
            "database": database_check(session_factory),
            "qdrant": http_check("http://127.0.0.1:9/readyz"),
        },
    )
    transport = httpx.ASGITransport(app=create_app(container))
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as http:
        yield http


async def test_documents_lists_the_corpus_with_effective_dates(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/documents")

    assert response.status_code == 200
    [document] = response.json()
    assert document["so_hieu"] == SO_HIEU
    assert document["effective_date"] == "2014-07-01"
    assert document["chunks"] == 1


async def test_chunk_returns_verbatim_text_and_its_place_in_the_law(
    client: httpx.AsyncClient,
) -> None:
    chunk_id = chunk_uuid(document_uuid(SO_HIEU), "dieu-100")

    response = await client.get(f"/api/v1/chunks/{chunk_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["so_hieu"] == SO_HIEU
    assert body["document_name"] == "Luật Đất đai"
    assert body["dieu"] == "100"
    assert body["khoan"] == [1, 2]
    assert body["location"] == (
        "Chương VII. ĐĂNG KÝ ĐẤT ĐAI › Điều 100. Cấp Giấy chứng nhận cho hộ gia đình, cá nhân"
    )
    assert "1. Hộ gia đình, cá nhân đang sử dụng đất ổn định" in body["text"]
    assert "context_text" not in body


async def test_unknown_chunk_is_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/chunks/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_readyz_is_503_when_qdrant_is_down(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/readyz")

    assert response.status_code == 503
    checks = response.json()["checks"]
    assert checks["database"] == "ok"
    assert checks["qdrant"].startswith("error:")
