import asyncio
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Any

import typer
from qdrant_client import AsyncQdrantClient

from lawqa.core.config import IngestionSettings, get_settings
from lawqa.db.session import create_engine, create_session_factory
from lawqa.eval.compare import compare_reports
from lawqa.eval.dataset import load_dataset
from lawqa.eval.generation_runner import run_generation_eval
from lawqa.eval.judge import Judge, JudgeConfigError, check_judge_config
from lawqa.eval.report import write_report
from lawqa.eval.runner import run_retrieval_eval
from lawqa.generation.llm_client import LLMClient
from lawqa.ingestion.chunker import chunk_document
from lawqa.ingestion.indexer import QdrantIndexer
from lawqa.ingestion.integrity import IntegrityError
from lawqa.ingestion.legal_parser import parse_file
from lawqa.ingestion.metadata import MetadataError
from lawqa.ingestion.report import format_report
from lawqa.ingestion.service import IndexingError, IngestService
from lawqa.ingestion.store import DocumentExistsError, list_documents
from lawqa.ingestion.tokens import HFTokenCounter
from lawqa.pipelines.base import DoneEvent, ErrorEvent, Query, SourcesEvent, TokenEvent
from lawqa.pipelines.hybrid import HybridRAGPipeline, PipelineSettings
from lawqa.retrieval.encoder_client import EncoderClient, EncoderError
from lawqa.retrieval.hybrid import HybridRetriever, RetrievalMode, RetrievalSettings

app = typer.Typer(help="Law QA — công cụ vận hành (nạp văn bản, tìm kiếm, hỏi đáp, đánh giá).")
documents_app = typer.Typer(help="Xem và quản lý văn bản đã nạp.")
app.add_typer(documents_app, name="documents")
eval_app = typer.Typer(help="Đánh giá chất lượng trên bộ câu hỏi chuẩn.")
app.add_typer(eval_app, name="eval")

_REPO = Path(__file__).resolve().parents[3]

_OPERATOR_ERRORS = (
    JudgeConfigError,
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


@asynccontextmanager
async def _retriever() -> AsyncIterator[HybridRetriever]:
    settings = get_settings()
    qdrant = AsyncQdrantClient(url=settings.qdrant_url)
    encoder = EncoderClient(settings.model_server_url)
    try:
        yield HybridRetriever(
            qdrant, encoder, RetrievalSettings(collection=settings.qdrant_collection)
        )
    finally:
        await encoder.aclose()
        await qdrant.close()


@asynccontextmanager
async def _pipeline() -> AsyncIterator[HybridRAGPipeline]:
    settings = get_settings()
    llm = LLMClient(
        settings.llm_base_url,
        settings.llm_model,
        settings.llm_api_key,
        api_style=settings.llm_api_style,
        num_ctx=settings.llm_num_ctx,
    )
    try:
        async with _retriever() as retriever:
            yield HybridRAGPipeline(
                retriever=retriever,
                llm=llm,
                counter=HFTokenCounter(settings.tokenizer_name),
                settings=PipelineSettings(
                    context_max_tokens=settings.context_max_tokens,
                    max_answer_tokens=settings.max_answer_tokens,
                    max_chunks=settings.max_context_chunks,
                ),
            )
    finally:
        await llm.aclose()


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


@app.command()
def search(
    query: str,
    mode: Annotated[str, typer.Option(help="hybrid | dense | bm25")] = "hybrid",
    top_k: Annotated[int, typer.Option("--top-k", help="Số kết quả hiển thị")] = 10,
    on: Annotated[
        str | None, typer.Option("--on", help="Ngày tham chiếu YYYY-MM-DD (mặc định hôm nay)")
    ] = None,
) -> None:
    """Tìm kiếm thử (không qua LLM) để kiểm tra retrieval."""
    if mode not in ("hybrid", "dense", "bm25"):
        raise typer.BadParameter("mode phải là hybrid, dense hoặc bm25")
    reference_date = date.fromisoformat(on) if on else date.today()
    retrieval_mode: RetrievalMode = mode  # type: ignore[assignment]

    async def run() -> None:
        async with _retriever() as retriever:
            results = await retriever.search([query], reference_date, mode=retrieval_mode)
        for rank, chunk in enumerate(results[:top_k], start=1):
            snippet = chunk.text.replace("\n", " ")[:110]
            typer.echo(
                f"{rank:>2}. {chunk.score:.4f}  {chunk.path:<18} Điều {chunk.article_number}. "
                f"{chunk.article_title[:60]}\n      {snippet}"
            )

    _run(run())


@app.command()
def ask(
    question: str,
    on: Annotated[
        str | None, typer.Option("--on", help="Ngày tham chiếu YYYY-MM-DD (mặc định hôm nay)")
    ] = None,
) -> None:
    """Hỏi đáp end-to-end: tìm kiếm hybrid → LLM → câu trả lời có trích dẫn."""
    query = Query(text=question, **({"reference_date": date.fromisoformat(on)} if on else {}))

    async def run() -> None:
        sources: SourcesEvent | None = None
        async with _pipeline() as pipeline:
            async for event in pipeline.answer(query):
                if isinstance(event, SourcesEvent):
                    sources = event
                elif isinstance(event, TokenEvent):
                    typer.echo(event.delta, nl=False)
                elif isinstance(event, ErrorEvent):
                    typer.echo(f"\n[{event.code}] {event.message}", err=True)
                    raise typer.Exit(code=1)
                elif isinstance(event, DoneEvent):
                    if not event.model:
                        typer.echo(event.answer, nl=False)
                    typer.echo(f"\n\n{event.disclaimer}")
                    if sources:
                        typer.echo("\nNguồn:")
                        for source in sources.sources:
                            mark = "*" if source.n in event.citations else " "
                            typer.echo(
                                f" {mark}[{source.n}] {source.so_hieu} Điều {source.dieu}. "
                                f"{source.title[:70]}"
                            )
                    if event.invalid_citations:
                        typer.echo(f"Trích dẫn không hợp lệ đã loại: {event.invalid_citations}")
                    typer.echo(f"Model: {event.model} · độ trễ (ms): {event.latency_ms}")

    _run(run())


@eval_app.command("retrieval")
def eval_retrieval(
    dataset: Annotated[
        Path, typer.Option("--set", exists=True, dir_okay=False, help="Tệp .jsonl")
    ] = _REPO / "eval" / "datasets" / "seed.jsonl",
    modes: Annotated[str, typer.Option(help="Các chế độ, cách nhau bởi dấu phẩy")] = (
        "dense,bm25,hybrid"
    ),
    on: Annotated[str | None, typer.Option("--on", help="Ngày tham chiếu YYYY-MM-DD")] = None,
    out: Annotated[Path, typer.Option(help="Thư mục kết quả")] = _REPO / "eval" / "results",
    min_recall: Annotated[
        float, typer.Option(help="Thoát lỗi nếu Recall@10 của chế độ cuối thấp hơn mức này")
    ] = 0.0,
) -> None:
    """Đo Recall@5/10, MRR@10, nDCG@10 cho từng chế độ tìm kiếm (ablation)."""
    mode_list = [mode.strip() for mode in modes.split(",") if mode.strip()]
    if not set(mode_list) <= {"dense", "bm25", "hybrid"}:
        raise typer.BadParameter("modes chỉ gồm dense, bm25, hybrid")
    reference_date = date.fromisoformat(on) if on else date.today()
    settings = get_settings()

    async def run() -> None:
        async with _retriever() as retriever:
            report = await run_retrieval_eval(
                load_dataset(dataset),
                retriever,
                mode_list,
                reference_date,
                config={
                    "retrieval": RetrievalSettings(
                        collection=settings.qdrant_collection
                    ).model_dump(),
                    "chunk_max_tokens": settings.chunk_max_tokens,
                    "tokenizer": settings.tokenizer_name,
                },
                dataset=dataset.name,
            )
        json_path, md_path = write_report(report, out)
        for mode in report.modes:
            values = " · ".join(f"{k} {v:.3f}" for k, v in mode.overall.items())
            typer.echo(f"{mode.mode:<7} {values}")
        typer.echo(f"Báo cáo: {md_path}\nDữ liệu: {json_path}")
        last = report.modes[-1].overall.get("recall@10", 0.0)
        if last < min_recall:
            typer.echo(f"Recall@10 {last:.3f} < ngưỡng {min_recall}", err=True)
            raise typer.Exit(code=1)

    _run(run())


@eval_app.command("generation")
def eval_generation(
    dataset: Annotated[
        Path, typer.Option("--set", exists=True, dir_okay=False, help="Tệp .jsonl")
    ] = _REPO / "eval" / "datasets" / "seed.jsonl",
    on: Annotated[str | None, typer.Option("--on", help="Ngày tham chiếu YYYY-MM-DD")] = None,
    out: Annotated[Path, typer.Option(help="Thư mục kết quả")] = _REPO / "eval" / "results",
    allow_self_judge: Annotated[
        bool, typer.Option("--allow-self-judge", help="Cho phép judge trùng model được chấm")
    ] = False,
) -> None:
    """Sinh câu trả lời cho cả bộ câu hỏi rồi chấm bằng LLM judge + metric tính bằng code."""
    settings = get_settings()
    if not settings.judge_model or not settings.judge_base_url:
        typer.echo("Thiếu JUDGE_BASE_URL / JUDGE_MODEL trong .env", err=True)
        raise typer.Exit(code=1)
    reference_date = date.fromisoformat(on) if on else date.today()

    async def run() -> None:
        assert settings.judge_model and settings.judge_base_url
        check_judge_config(
            generator={"base_url": settings.llm_base_url, "model": settings.llm_model},
            judge={"base_url": settings.judge_base_url, "model": settings.judge_model},
            allow_self_judge=allow_self_judge,
        )
        judge_llm = LLMClient(
            settings.judge_base_url,
            settings.judge_model,
            settings.judge_api_key,
            api_style=settings.judge_api_style,
            num_ctx=settings.llm_num_ctx,
        )
        try:
            async with _pipeline() as pipeline:
                report = await run_generation_eval(
                    load_dataset(dataset),
                    pipeline,
                    Judge(judge_llm),
                    reference_date,
                    config={
                        "llm_model": settings.llm_model,
                        "judge_model": settings.judge_model,
                        "context_max_tokens": settings.context_max_tokens,
                        "max_context_chunks": settings.max_context_chunks,
                        "max_answer_tokens": settings.max_answer_tokens,
                        "retrieval": RetrievalSettings(
                            collection=settings.qdrant_collection
                        ).model_dump(),
                    },
                    dataset=dataset.name,
                )
        finally:
            await judge_llm.aclose()
        json_path, md_path = write_report(report, out)
        for key, value in report.overall.items():
            typer.echo(f"{key:<24} {value:.3f}")
        typer.echo(f"Báo cáo: {md_path}\nDữ liệu: {json_path}")

    _run(run())


@eval_app.command("compare")
def eval_compare(
    reports: Annotated[list[Path], typer.Argument(help="Các tệp kết quả .json")],
    out: Annotated[Path, typer.Option(help="Thư mục kết quả")] = _REPO / "eval" / "results",
) -> None:
    """So sánh nhiều lần đánh giá, đặt các chỉ số cạnh nhau."""
    markdown = compare_reports([path for path in reports if path.suffix == ".json"])
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"compare-{datetime.now(UTC):%Y%m%d-%H%M%S}.md"
    target.write_text(markdown, encoding="utf-8")
    typer.echo(markdown)
    typer.echo(f"Đã lưu: {target}")
