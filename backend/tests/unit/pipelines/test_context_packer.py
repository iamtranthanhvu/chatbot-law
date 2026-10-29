from lawqa.retrieval.context_packer import pack_context
from tests.unit.pipelines.conftest import WordCounter, make_chunk


def test_groups_chunks_of_the_same_article_in_reading_order() -> None:
    chunks = [
        make_chunk("100", "khoản năm", ordinal=2, score=0.9),
        make_chunk("101", "điều một trăm lẻ một", score=0.8),
        make_chunk("100", "khoản một", ordinal=0, score=0.7),
    ]

    sources = pack_context(chunks, WordCounter(), max_tokens=1000)

    assert [s.article_number for s in sources] == ["100", "101"]
    assert [s.n for s in sources] == [1, 2]
    assert [c.ordinal for c in sources[0].chunks] == [0, 2]
    assert "khoản một\n…\nkhoản năm" in sources[0].text


def test_articles_are_sorted_by_number_not_by_string() -> None:
    chunks = [make_chunk("100", "a"), make_chunk("9", "b"), make_chunk("21", "c")]

    sources = pack_context(chunks, WordCounter(), max_tokens=1000)

    assert [s.article_number for s in sources] == ["9", "21", "100"]


def test_source_header_names_the_document_and_article() -> None:
    sources = pack_context(
        [make_chunk("100", "nội dung", title="Cấp Giấy chứng nhận")], WordCounter(), 1000
    )

    assert sources[0].text.splitlines()[0] == (
        "[1] Luật Đất đai (45/2013/QH13) — Điều 100. Cấp Giấy chứng nhận"
    )


def test_most_relevant_chunks_are_kept_within_the_budget() -> None:
    chunks = [
        make_chunk("1", "rất liên quan " * 20, score=0.9),
        make_chunk("2", "ít liên quan " * 20, score=0.2),
        make_chunk("3", "liên quan vừa " * 20, score=0.5),
    ]

    sources = pack_context(chunks, WordCounter(), max_tokens=140)

    assert [s.article_number for s in sources] == ["1", "3"]
    assert sum(WordCounter().count(s.text) for s in sources) <= 140


def test_no_chunks_gives_no_sources() -> None:
    assert pack_context([], WordCounter(), 1000) == []
