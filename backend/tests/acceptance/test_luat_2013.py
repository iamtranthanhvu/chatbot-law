from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from lawqa.cli import app
from lawqa.ingestion.chunker import chunk_document
from lawqa.ingestion.docx_reader import read_paragraphs
from lawqa.ingestion.legal_parser import parse_file
from lawqa.ingestion.metadata import DocumentSections, extract_metadata, split_sections
from lawqa.ingestion.models import Heading, ParsedDocument
from lawqa.ingestion.normalize import normalize_lines
from lawqa.ingestion.tokens import HFTokenCounter

RAW_FILE = Path(__file__).resolve().parents[3] / "raw_data" / "Luật-45-2013-QH13.docx"

pytestmark = [
    pytest.mark.corpus,
    pytest.mark.skipif(not RAW_FILE.exists(), reason="raw_data/ not available"),
]


@pytest.fixture(scope="module")
def sections() -> DocumentSections:
    return split_sections(normalize_lines(read_paragraphs(RAW_FILE)))


def test_metadata(sections: DocumentSections) -> None:
    meta = extract_metadata(sections)

    assert meta.so_hieu == "45/2013/QH13"
    assert meta.name == "Luật Đất đai"
    assert meta.issuer == "Quốc hội"
    assert meta.passed_date == date(2013, 11, 29)
    assert meta.effective_date == date(2014, 7, 1)


def test_body_boundaries(sections: DocumentSections) -> None:
    assert sections.body[0] == "Chương 1."
    assert sections.body[-1] == "Chính phủ quy định chi tiết các điều, khoản được giao trong Luật."
    assert not any("Nguyễn Sinh Hùng" in line for line in sections.body)


@pytest.fixture(scope="module")
def parsed() -> ParsedDocument:
    return parse_file(RAW_FILE)


def test_structure_counts(parsed: ParsedDocument) -> None:
    structure = parsed.structure

    assert len(structure.chapters) == 14
    assert len(structure.articles) == 212
    assert [a.number for a in structure.articles] == [str(n) for n in range(1, 213)]
    assert sum(1 for b in structure.blocks if isinstance(b, Heading) and b.kind == "muc") == 23
    assert structure.warnings == []


def test_article_40_clause_4_points_after_source_fix(parsed: ParsedDocument) -> None:
    clause_4 = parsed.structure.articles[39].clauses[3]

    assert [p.letter for p in clause_4.points] == ["a", "b", "c", "d", "đ", "e"]


def test_text_wrapped_in_word_smart_tags_is_not_lost(parsed: ParsedDocument) -> None:
    assert parsed.preamble[0] == "Căn cứ Hiến pháp nước Cộng hòa xã hội chủ nghĩa Việt Nam;"
    article_5 = parsed.structure.articles[4]
    assert "6. Người Việt Nam định cư ở nước ngoài theo quy định của pháp luật về quốc tịch;" in (
        article_5.all_lines()
    )


def test_unnumbered_paragraph_belongs_to_preceding_point(parsed: ParsedDocument) -> None:
    # Rule confirmed by a legal expert: everything after a marker, line breaks included,
    # belongs to that unit until the next marker of the same or a higher level.
    article_44_point_a = parsed.structure.articles[43].clauses[0].points[0]
    assert article_44_point_a.lines[1].startswith(
        "Bộ Tài nguyên và Môi trường có trách nhiệm giúp Hội đồng thẩm định"
    )

    article_29_point_b = parsed.structure.articles[28].clauses[3].points[1]
    assert article_29_point_b.lines[-1].startswith(
        "Bộ Tài nguyên và Môi trường, cơ quan quản lý đất đai của tỉnh"
    )


def test_chapter_title_spanning_two_lines(parsed: ParsedDocument) -> None:
    chapter_7 = parsed.structure.chapters[6]

    assert chapter_7.title == (
        "ĐĂNG KÝ ĐẤT ĐAI, CẤP GIẤY CHỨNG NHẬN QUYỀN SỬ DỤNG ĐẤT, "
        "QUYỀN SỞ HỮU NHÀ Ở VÀ TÀI SẢN KHÁC GẮN LIỀN VỚI ĐẤT"
    )


def test_article_100(parsed: ParsedDocument) -> None:
    article = parsed.structure.articles[99]

    assert article.title.startswith("Cấp Giấy chứng nhận quyền sử dụng đất")
    assert article.chapter_number == "7"
    assert [c.number for c in article.clauses] == [1, 2, 3, 4, 5]
    assert [p.letter for p in article.clauses[0].points] == ["a", "b", "c", "d", "đ", "e", "g"]


def test_dry_run_cli_reports_structure() -> None:
    result = CliRunner().invoke(app, ["ingest", str(RAW_FILE), "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "45/2013/QH13" in result.output
    assert "Điều: 212" in result.output


def test_chunks_respect_token_limit_and_keep_all_text(parsed: ParsedDocument) -> None:
    counter = HFTokenCounter("BAAI/bge-m3")
    chunks = chunk_document(parsed, counter, max_tokens=512)

    assert all(chunk.token_count <= 512 for chunk in chunks)
    assert len({chunk.path for chunk in chunks}) == len(chunks)
    for article in parsed.structure.articles:
        own = [c for c in chunks if c.article_number == article.number]
        rebuilt = " ".join(c.text for c in sorted(own, key=lambda c: c.order)).split()
        assert rebuilt == " ".join(article.all_lines()[1:]).split(), f"Điều {article.number}"
