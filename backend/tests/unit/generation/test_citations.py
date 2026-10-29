from lawqa.generation.citations import validate_citations


def test_keeps_valid_and_drops_out_of_range_citations() -> None:
    text = "Theo quy định [1][7], hộ gia đình được cấp giấy [3]."
    check = validate_citations(text, source_count=3)

    assert check.text == "Theo quy định [1], hộ gia đình được cấp giấy [3]."
    assert check.cited == [1, 3]
    assert check.invalid == [7]


def test_cleans_numbers_inside_a_grouped_citation() -> None:
    check = validate_citations("Căn cứ [2, 9; 1].", source_count=2)

    assert check.text == "Căn cứ [2, 1]."
    assert check.cited == [2, 1]
    assert check.invalid == [9]


def test_zero_is_never_a_valid_source() -> None:
    check = validate_citations("Sai [0].", source_count=5)

    assert check.text == "Sai."
    assert check.cited == []
    assert check.invalid == [0]


def test_cited_lists_each_source_once_in_order_of_first_use() -> None:
    check = validate_citations("A [2]. B [1]. C [2].", source_count=2)

    assert check.cited == [2, 1]
    assert check.invalid == []


def test_text_without_citations_is_unchanged() -> None:
    check = validate_citations("Không đủ căn cứ để trả lời.", source_count=0)

    assert check.text == "Không đủ căn cứ để trả lời."
    assert check.cited == []
