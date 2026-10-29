from datetime import date
from pathlib import Path

import pytest

from lawqa.ingestion.docx_reader import read_paragraphs
from lawqa.ingestion.metadata import DocumentSections, extract_metadata, split_sections
from lawqa.ingestion.normalize import normalize_lines

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
