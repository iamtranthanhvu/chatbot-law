import pytest

from lawqa.understanding.citation_regex import CitationRef, extract_citations


@pytest.mark.parametrize("number", [str(n) for n in range(1, 213)])
def test_every_article_number_is_recognised(number: str) -> None:
    assert extract_citations(f"Điều {number} Luật Đất đai quy định gì?") == [
        CitationRef(dieu=number)
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("khoản 2 Điều 5", CitationRef(dieu="5", khoan=2)),
        ("Khoản 1 Điều 126 Luật Đất đai", CitationRef(dieu="126", khoan=1)),
        ("điểm a khoản 1 Điều 100", CitationRef(dieu="100", khoan=1, diem="a")),
        ("điểm đ khoản 1 Điều 100", CitationRef(dieu="100", khoan=1, diem="đ")),
        ("ĐIỀU 64", CitationRef(dieu="64")),
        ("dieu 100 luat dat dai", CitationRef(dieu="100")),
        ("khoan 3 dieu 12", CitationRef(dieu="12", khoan=3)),
        ("diem d khoan 1 dieu 57", CitationRef(dieu="57", khoan=1, diem="d")),
        (
            "Điều 100 Luật số 45/2013/QH13",
            CitationRef(dieu="100", so_hieu="45/2013/QH13"),
        ),
    ],
)
def test_clause_point_and_document_references(text: str, expected: CitationRef) -> None:
    assert extract_citations(text) == [expected]


def test_several_references_in_one_question_keep_order_without_duplicates() -> None:
    refs = extract_citations("So sánh Điều 100 và Điều 101, rồi xem lại Điều 100.")

    assert refs == [CitationRef(dieu="100"), CitationRef(dieu="101")]


@pytest.mark.parametrize(
    "text",
    [
        "Điều kiện chuyển nhượng quyền sử dụng đất là gì?",
        "Tôi xây nhà trên đất ruộng có bị phạt không?",
        "mục đích sử dụng đất",
        "điều 0 không tồn tại",
    ],
)
def test_questions_without_references(text: str) -> None:
    assert extract_citations(text) == []
