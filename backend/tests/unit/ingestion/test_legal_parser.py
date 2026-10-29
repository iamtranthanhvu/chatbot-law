import pytest

from lawqa.ingestion.integrity import IntegrityError, check_integrity
from lawqa.ingestion.legal_parser import parse_body
from lawqa.ingestion.models import Article, Heading

BODY = [
    "Chương 1.",
    "QUY ĐỊNH CHUNG",
    "Điều 1. Phạm vi điều chỉnh",
    "Luật này quy định về chế độ sở hữu đất đai.",
    "Điều 2. Đối tượng áp dụng",
    "1. Cơ quan nhà nước thực hiện quyền hạn.",
    "2. Người sử dụng đất gồm:",
    "a) Hộ gia đình;",
    "b) Cá nhân;",
    "Trường hợp cá nhân là người nước ngoài thì áp dụng điểm này.",
    "c) Tổ chức;",
    "d) Cơ sở tôn giáo;",
    "đ) Cộng đồng dân cư.",
    "Chương 2.",
    "QUYỀN VÀ TRÁCH NHIỆM",
    "CỦA NHÀ NƯỚC",
    "MỤC 1. QUYỀN CỦA NHÀ NƯỚC",
    "Điều 3. Quyền của Nhà nước",
    "Nhà nước có các quyền sau đây:",
    "a) Quyết định quy hoạch;",
    "b) Quyết định mục đích sử dụng đất.",
    "Mục 2",
    "TRÁCH NHIỆM CỦA NHÀ NƯỚC",
    "Điều 4. Trách nhiệm",
    "1. Bảo đảm quyền.",
    "1. Dòng này trùng số khoản nên được giữ là nội dung của khoản 1.",
    "3. Khoản nhảy số (bản gốc thiếu khoản 2) vẫn được nhận.",
    "a) Điểm đầu;",
    "c) Điểm nhảy chữ vẫn được nhận.",
]


def _articles(blocks: list[Article | Heading]) -> list[Article]:
    return [block for block in blocks if isinstance(block, Article)]


def test_chapters_with_title_on_following_uppercase_lines() -> None:
    result = parse_body(BODY)
    chapters = [b for b in result.blocks if isinstance(b, Heading) and b.kind == "chuong"]

    assert [(c.number, c.title) for c in chapters] == [
        ("1", "QUY ĐỊNH CHUNG"),
        ("2", "QUYỀN VÀ TRÁCH NHIỆM CỦA NHÀ NƯỚC"),
    ]


def test_sections_with_inline_or_next_line_title() -> None:
    result = parse_body(BODY)
    sections = [b for b in result.blocks if isinstance(b, Heading) and b.kind == "muc"]

    assert [(s.number, s.title) for s in sections] == [
        ("1", "QUYỀN CỦA NHÀ NƯỚC"),
        ("2", "TRÁCH NHIỆM CỦA NHÀ NƯỚC"),
    ]


def test_article_clauses_and_points() -> None:
    article = _articles(parse_body(BODY).blocks)[1]

    assert (article.number, article.title) == ("2", "Đối tượng áp dụng")
    assert article.chapter_number == "1"
    assert [c.number for c in article.clauses] == [1, 2]
    assert [p.letter for p in article.clauses[1].points] == ["a", "b", "c", "d", "đ"]


def test_unnumbered_paragraph_attaches_to_deepest_open_unit() -> None:
    article = _articles(parse_body(BODY).blocks)[1]

    assert article.clauses[1].points[1].lines == [
        "b) Cá nhân;",
        "Trường hợp cá nhân là người nước ngoài thì áp dụng điểm này.",
    ]


def test_points_directly_under_article_and_context() -> None:
    article = _articles(parse_body(BODY).blocks)[2]

    assert article.intro == ["Nhà nước có các quyền sau đây:"]
    assert [p.letter for p in article.points] == ["a", "b"]
    assert article.section_number == "1"
    assert article.chapter_title == "QUYỀN VÀ TRÁCH NHIỆM CỦA NHÀ NƯỚC"


def test_repeated_number_is_kept_as_text_with_warning() -> None:
    result = parse_body(BODY)
    article = _articles(result.blocks)[3]

    assert article.clauses[0].lines[-1].startswith("1. Dòng này trùng")
    assert any("Điều 4" in w and "khoản 1" in w for w in result.warnings)


def test_forward_gaps_are_accepted_with_warning() -> None:
    result = parse_body(BODY)
    article = _articles(result.blocks)[3]

    assert [c.number for c in article.clauses] == [1, 3]
    assert [p.letter for p in article.clauses[1].points] == ["a", "c"]
    assert any("khoản 3" in w for w in result.warnings)
    assert any("điểm c)" in w for w in result.warnings)


def test_integrity_accepts_well_formed_body() -> None:
    check_integrity(parse_body(BODY), BODY)


def test_integrity_rejects_missing_article() -> None:
    body = [line for line in BODY if not line.startswith("Điều 3")]
    body = [line.replace("Điều 4.", "Điều 5.") for line in body]

    with pytest.raises(IntegrityError, match="Điều 3"):
        check_integrity(parse_body(body), body)


def test_integrity_rejects_text_outside_any_article() -> None:
    body = ["Chương 1.", "QUY ĐỊNH CHUNG", "Đoạn văn lạc chỗ.", *BODY[2:]]

    with pytest.raises(IntegrityError, match="Đoạn văn lạc chỗ"):
        check_integrity(parse_body(body), body)
