from datetime import date

import pytest

from lawqa.ingestion.metadata import MetadataError, extract_metadata, split_sections

LUAT_2013 = [
    "QUỐC HỘI",
    "----------",
    "Luật số: 45/2013/QH13",
    "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM",
    "Độc lập - Tự do - Hạnh phúc",
    "-----------------------------",
    "LUẬT",
    "ĐẤT ĐAI",
    "Căn cứ Hiến pháp nước Cộng hòa xã hội chủ nghĩa Việt Nam;",
    "Quốc hội ban hành Luật đất đai,",
    "Chương 1.",
    "QUY ĐỊNH CHUNG",
    "Điều 1. Phạm vi điều chỉnh",
    "Luật này quy định về chế độ sở hữu đất đai.",
    "Điều 211. Hiệu lực thi hành",
    "1. Luật này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2014.",
    "Điều 212. Quy định chi tiết",
    "Chính phủ quy định chi tiết các điều, khoản được giao trong Luật.",
    "Luật này đã được Quốc hội nước Cộng hòa xã hội chủ nghĩa Việt Nam khóa XIII, "
    "kỳ họp thứ 6 thông qua ngày 29 tháng 11 năm 2013.",
    "CHỦ TỊCH QUỐC HỘI",
    "Nguyễn Sinh Hùng",
]

LUAT_SUA_DOI_2024 = [
    "QUỐC HỘI",
    "Luật số: 43/2024/QH15",
    "LUẬT",
    "Sửa đổi, bổ sung một số điều",
    "của Luật Đất đai số 31/2024/QH15, Luật Nhà ở số 27/2023/QH15",
    "Căn cứ Hiến pháp nước Cộng hòa xã hội chủ nghĩa Việt Nam;",
    "Điều 1. Sửa đổi, bổ sung một số điều của Luật Đất đai số 31/2024/QH15",
    "1. Sửa đổi, bổ sung khoản 1 Điều 252 như sau:",
    "“1. Luật này có hiệu lực thi hành từ ngày 01 tháng 8 năm 2024.”.",
    "Điều 5. Hiệu lực thi hành",
    "Luật này có hiệu lực thi hành từ ngày 01 tháng 8 năm 2024.",
    "Luật này được Quốc hội nước Cộng hòa xã hội chủ nghĩa Việt Nam khóa XV, "
    "kỳ họp thứ 7 thông qua ngày 29 tháng 6 năm 2024.",
    "CHỦ TỊCH QUỐC HỘI",
]


def test_split_sections_separates_header_body_and_footer() -> None:
    sections = split_sections(LUAT_2013)

    assert sections.header[2] == "Luật số: 45/2013/QH13"
    assert sections.preamble == [
        "Căn cứ Hiến pháp nước Cộng hòa xã hội chủ nghĩa Việt Nam;",
        "Quốc hội ban hành Luật đất đai,",
    ]
    assert sections.body[0] == "Chương 1."
    assert sections.body[-1] == "Chính phủ quy định chi tiết các điều, khoản được giao trong Luật."
    assert sections.footer[0].startswith("Luật này đã được Quốc hội")
    assert "Nguyễn Sinh Hùng" not in sections.body


def test_extracts_metadata_of_original_law() -> None:
    meta = extract_metadata(split_sections(LUAT_2013))

    assert meta.so_hieu == "45/2013/QH13"
    assert meta.doc_type == "Luật"
    assert meta.title == "Đất đai"
    assert meta.name == "Luật Đất đai"
    assert meta.issuer == "Quốc hội"
    assert meta.passed_date == date(2013, 11, 29)
    assert meta.effective_date == date(2014, 7, 1)


def test_effective_date_ignores_quoted_amendment_text() -> None:
    meta = extract_metadata(split_sections(LUAT_SUA_DOI_2024))

    assert meta.so_hieu == "43/2024/QH15"
    assert meta.title == (
        "Sửa đổi, bổ sung một số điều của Luật Đất đai số 31/2024/QH15, Luật Nhà ở số 27/2023/QH15"
    )
    assert meta.effective_date == date(2024, 8, 1)
    assert meta.passed_date == date(2024, 6, 29)


def test_missing_document_number_is_an_error() -> None:
    lines = [line for line in LUAT_2013 if not line.startswith("Luật số")]

    with pytest.raises(MetadataError, match="số hiệu"):
        extract_metadata(split_sections(lines))
