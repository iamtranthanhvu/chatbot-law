import unicodedata

from lawqa.ingestion.normalize import normalize_lines, normalize_text


def test_converts_decomposed_vietnamese_to_nfc() -> None:
    decomposed = unicodedata.normalize("NFD", "Quyền sử dụng đất")

    result = normalize_text(decomposed)

    assert result == "Quyền sử dụng đất"
    assert unicodedata.is_normalized("NFC", result)


def test_collapses_whitespace_and_special_spaces() -> None:
    assert normalize_text("  Điều 1.\tPhạm   vi​ điều chỉnh \n") == "Điều 1. Phạm vi điều chỉnh"


def test_replaces_icelandic_eth_with_vietnamese_d() -> None:
    assert normalize_text("Ðiều 5 ðất") == "Điều 5 đất"


def test_normalize_lines_drops_empty_lines() -> None:
    assert normalize_lines(["Điều 1.", "   ", " ", "Nội dung"]) == ["Điều 1.", "Nội dung"]
