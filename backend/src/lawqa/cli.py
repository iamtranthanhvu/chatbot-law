from pathlib import Path
from typing import Annotated

import typer

from lawqa.core.config import IngestionSettings
from lawqa.ingestion.chunker import chunk_document
from lawqa.ingestion.integrity import IntegrityError
from lawqa.ingestion.legal_parser import parse_file
from lawqa.ingestion.metadata import MetadataError
from lawqa.ingestion.report import format_report
from lawqa.ingestion.tokens import HFTokenCounter

app = typer.Typer(help="Law QA — công cụ vận hành (nạp văn bản, tìm kiếm, hỏi đáp, đánh giá).")


@app.callback()
def main() -> None:
    """Law QA operator CLI."""


@app.command()
def ingest(
    path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="Tệp .docx")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Chỉ phân tích, không ghi")] = False,
) -> None:
    """Phân tích và nạp một văn bản pháp luật."""
    try:
        document = parse_file(path)
    except (IntegrityError, MetadataError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error

    settings = IngestionSettings()
    counter = HFTokenCounter(settings.tokenizer_name)
    chunks = chunk_document(document, counter, settings.chunk_max_tokens)
    typer.echo(format_report(document, chunks))
    if not dry_run:
        typer.echo(
            "Nạp vào cơ sở dữ liệu chưa được hỗ trợ ở phiên bản này; dùng --dry-run.", err=True
        )
        raise typer.Exit(code=2)
