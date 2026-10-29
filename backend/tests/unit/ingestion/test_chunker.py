from datetime import date

from lawqa.ingestion.chunker import chunk_document
from lawqa.ingestion.legal_parser import parse_body
from lawqa.ingestion.metadata import DocumentMetadata
from lawqa.ingestion.models import ParsedDocument


class WordCounter:
    def count(self, text: str) -> int:
        return len(text.split())


META = DocumentMetadata(
    so_hieu="45/2013/QH13",
    doc_type="Luật",
    title="Đất đai",
    name="Luật Đất đai",
    issuer="Quốc hội",
    passed_date=date(2013, 11, 29),
    effective_date=date(2014, 7, 1),
)


def _document(body: list[str]) -> ParsedDocument:
    return ParsedDocument(
        metadata=META, preamble=[], structure=parse_body(body), sha256="x", source_file="f.docx"
    )


def _words(n: int, word: str = "đất") -> str:
    return " ".join([word] * n)


SHORT = ["Chương 1.", "QUY ĐỊNH CHUNG", "Điều 1. Phạm vi điều chỉnh", "Luật này quy định về đất."]


def test_short_article_is_one_chunk_with_breadcrumb_context() -> None:
    chunks = chunk_document(_document(SHORT), WordCounter(), max_tokens=100)

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.path == "dieu-1"
    assert chunk.text == "Luật này quy định về đất."
    assert chunk.context_text.splitlines()[0] == (
        "Luật Đất đai (45/2013/QH13) > Chương 1. Quy định chung > Điều 1. Phạm vi điều chỉnh"
    )
    assert chunk.context_text.endswith("Luật này quy định về đất.")
    assert chunk.token_count == WordCounter().count(chunk.context_text)


LONG = [
    "Chương 1.",
    "QUY ĐỊNH CHUNG",
    "Điều 2. Quy định dài",
    "Phần mở đầu.",
    f"1. {_words(20)}",
    f"2. {_words(20)}",
    f"3. Khoản có điểm: {_words(5)}",
    f"a) {_words(25)}",
    f"b) {_words(25)}",
    f"c) {_words(25)}",
    f"4. {_words(5)}",
    f"5. {_words(120)}",
]


def test_long_article_is_split_without_losing_or_duplicating_lines() -> None:
    document = _document(LONG)
    chunks = chunk_document(document, WordCounter(), max_tokens=60)

    assert all(chunk.token_count <= 60 for chunk in chunks)
    rebuilt = [line for chunk in chunks for line in chunk.text.split("\n")]
    rebuilt_words = " ".join(rebuilt).split()
    original_words = " ".join(document.structure.articles[0].all_lines()[1:]).split()
    assert rebuilt_words == original_words


def test_split_chunks_record_clauses_and_points() -> None:
    chunks = chunk_document(_document(LONG), WordCounter(), max_tokens=60)

    assert [c.path for c in chunks] == [f"dieu-2/p{i}" for i in range(1, len(chunks) + 1)]
    assert chunks[0].clauses[:1] == [1]
    point_chunks = [c for c in chunks if "3.b" in c.points]
    assert point_chunks and 3 in point_chunks[0].clauses


def test_point_sub_chunks_carry_clause_lead_in_context() -> None:
    chunks = chunk_document(_document(LONG), WordCounter(), max_tokens=60)

    chunk_with_c = next(c for c in chunks if "3.c" in c.points and "3.a" not in c.points)
    assert "Khoản 3: 3. Khoản có điểm:" in chunk_with_c.context_text


def test_paths_are_deterministic() -> None:
    first = chunk_document(_document(LONG), WordCounter(), max_tokens=60)
    second = chunk_document(_document(LONG), WordCounter(), max_tokens=60)

    assert [c.model_dump() for c in first] == [c.model_dump() for c in second]
