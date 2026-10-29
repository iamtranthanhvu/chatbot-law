import asyncio
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

import typer
from qdrant_client import AsyncQdrantClient

from lawqa.core.config import IngestionSettings, get_settings
from lawqa.db.session import create_engine, create_session_factory
from lawqa.ingestion.chunker import chunk_document
from lawqa.ingestion.indexer import QdrantIndexer
from lawqa.ingestion.integrity import IntegrityError
from lawqa.ingestion.legal_parser import parse_file
from lawqa.ingestion.metadata import MetadataError
from lawqa.ingestion.report import format_report
from lawqa.ingestion.service import IndexingError, IngestService
from lawqa.ingestion.store import DocumentExistsError, list_documents
from lawqa.ingestion.tokens import HFTokenCounter
from lawqa.retrieval.encoder_client import EncoderClient, EncoderError

app = typer.Typer(help="Law QA — công cụ vận hành (nạp văn bản, tìm kiếm, hỏi đáp, đánh giá).")
documents_app = typer.Typer(help="Xem và quản lý văn bản đã nạp.")
app.add_typer(documents_app, name="documents")

_OPERATOR_ERRORS = (
    IntegrityError,
    MetadataError,
    DocumentExistsError,
    EncoderError,
    IndexingError,
)


@app.callback()
def main() -> None:
    """Law QA operator CLI."""


@asynccontextmanager
async def _service() -> AsyncIterator[IngestService]:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    qdrant = AsyncQdrantClient(url=settings.qdrant_url)
    encoder = EncoderClient(settings.model_server_url)
    try:
        yield IngestService(
            session_factory=create_session_factory(engine),
            encoder=encoder,
            indexer=QdrantIndexer(qdrant, settings.qdrant_collection),
            counter=HFTokenCounter(settings.tokenizer_name),
            max_tokens=settings.chunk_max_tokens,
        )
    finally:
        await encoder.aclose()
        await qdrant.close()
        await engine.dispose()


def _run(coroutine: Coroutine[Any, Any, None]) -> None:
    try:
        asyncio.run(coroutine)
    except _OPERATOR_ERRORS as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error


@app.command()
def ingest(
    path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="Tệp .docx")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Chỉ phân tích, không ghi")] = False,
    replace: Annotated[
        bool, typer.Option("--replace", help="Thay văn bản cùng số hiệu đã có")
    ] = False,
) -> None:
    """Phân tích và nạp một văn bản pháp luật vào Postgres + Qdrant."""
    if dry_run:
        try:
            document = parse_file(path)
        except (IntegrityError, MetadataError) as error:
            typer.echo(str(error), err=True)
            raise typer.Exit(code=1) from error
        settings = IngestionSettings()
        chunks = chunk_document(
            document, HFTokenCounter(settings.tokenizer_name), settings.chunk_max_tokens
        )
        typer.echo(format_report(document, chunks))
        return

    async def run() -> None:
        async with _service() as service:
            report = await service.ingest(path, replace=replace)
        typer.echo(format_report(report.document, report.chunks))
        store = report.store
        avgdl = f" · BM25 avgdl {report.avgdl:.1f}" if report.avgdl else ""
        typer.echo(
            f"Kết quả: {store.status} · corpus_version {store.corpus_version}"
            f" · điều khoản {store.provisions} · chunk {store.chunks}"
            f" · đã index {report.indexed}{avgdl}"
        )

    _run(run())


@app.command()
def reindex() -> None:
    """Xây lại toàn bộ index Qdrant từ dữ liệu trong Postgres."""

    async def run() -> None:
        async with _service() as service:
            count = await service.reindex()
        typer.echo(f"Đã index lại {count} chunk.")

    _run(run())


@documents_app.command("list")
def documents_list() -> None:
    """Liệt kê văn bản đã nạp."""

    async def run() -> None:
        async with _service() as service:
            documents = await list_documents(service.session_factory)
        if not documents:
            typer.echo("Chưa có văn bản nào.")
        for doc in documents:
            effective = doc.effective_date.strftime("%d/%m/%Y") if doc.effective_date else "?"
            typer.echo(f"{doc.so_hieu}\t{doc.name}\thiệu lực {effective}\t{doc.chunks} chunk")

    _run(run())


@documents_app.command("show")
def documents_show(so_hieu: str) -> None:
    """Xem chi tiết một văn bản."""

    async def run() -> None:
        async with _service() as service:
            documents = await list_documents(service.session_factory)
        match = next((doc for doc in documents if doc.so_hieu == so_hieu), None)
        if match is None:
            typer.echo(f"Không có văn bản {so_hieu}.", err=True)
            raise typer.Exit(code=1)
        for key, value in match.model_dump().items():
            typer.echo(f"{key}: {value}")

    _run(run())


@documents_app.command("remove")
def documents_remove(
    so_hieu: str,
    yes: Annotated[bool, typer.Option("--yes", help="Không hỏi xác nhận")] = False,
) -> None:
    """Xóa một văn bản khỏi Postgres và Qdrant."""
    if not yes:
        typer.confirm(f"Xóa văn bản {so_hieu} khỏi Postgres và Qdrant?", abort=True)

    async def run() -> None:
        async with _service() as service:
            removed = await service.remove(so_hieu)
        if not removed:
            typer.echo(f"Không có văn bản {so_hieu}.", err=True)
            raise typer.Exit(code=1)
        typer.echo(f"Đã xóa {so_hieu}.")

    _run(run())
