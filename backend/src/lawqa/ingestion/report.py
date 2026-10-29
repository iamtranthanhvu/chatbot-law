import statistics
from datetime import date

from lawqa.ingestion.chunker import Chunk
from lawqa.ingestion.models import ParsedDocument


def format_report(document: ParsedDocument, chunks: list[Chunk]) -> str:
    meta = document.metadata
    structure = document.structure
    articles = structure.articles
    clauses = [clause for article in articles for clause in article.clauses]
    points = [p for a in articles for p in a.points] + [p for c in clauses for p in c.points]
    sections = [b for b in structure.blocks if b.block == "heading" and b.kind == "muc"]

    lines = [
        f"Văn bản: {meta.name} ({meta.so_hieu})",
        f"Tệp: {document.source_file} · sha256 {document.sha256[:12]}",
        f"Cơ quan ban hành: {meta.issuer or '?'} · Thông qua: {_fmt(meta.passed_date)}"
        f" · Hiệu lực: {_fmt(meta.effective_date)}",
        f"Cấu trúc: Chương: {len(structure.chapters)} · Mục: {len(sections)}"
        f" · Điều: {len(articles)} · Khoản: {len(clauses)} · Điểm: {len(points)}",
    ]
    if chunks:
        sizes = [chunk.token_count for chunk in chunks]
        split_articles = {chunk.article_number for chunk in chunks if "/" in chunk.path}
        lines.append(
            f"Chunk: {len(chunks)} · token min/trung vị/max: {min(sizes)}/"
            f"{int(statistics.median(sizes))}/{max(sizes)} · Điều phải tách: {len(split_articles)}"
        )
    if structure.warnings:
        lines.append(f"Cảnh báo ({len(structure.warnings)}):")
        lines.extend(f"  - {warning}" for warning in structure.warnings)
    else:
        lines.append("Cảnh báo: không có")
    return "\n".join(lines)


def _fmt(value: date | None) -> str:
    return value.strftime("%d/%m/%Y") if value else "không xác định"
