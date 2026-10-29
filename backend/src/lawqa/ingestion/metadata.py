import re
from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel, ConfigDict


class MetadataError(ValueError):
    pass


class DocumentMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    so_hieu: str
    doc_type: str
    title: str
    name: str
    issuer: str | None
    passed_date: date | None
    effective_date: date | None


@dataclass(frozen=True)
class DocumentSections:
    header: list[str]
    preamble: list[str]
    body: list[str]
    footer: list[str]


_BODY_START = re.compile(r"^(?:Phần|PHẦN|Chương|CHƯƠNG|Điều)\s+\S+")
_PREAMBLE_START = re.compile(r"^Căn cứ\b")
_FOOTER_START = re.compile(
    r"^(?:(?:Bộ luật|Luật|Nghị quyết|Pháp lệnh) này (?:đã )?được .*thông qua ngày"
    r"|TM\.|KT\.|Nơi nhận)"
)
_SO_HIEU = re.compile(r"số:\s*(\S+)", re.IGNORECASE)
_DATE_PHRASE = r"ngày (\d{1,2}) tháng (\d{1,2}) năm (\d{4})"
_PASSED = re.compile(rf"thông qua {_DATE_PHRASE}")
_EFFECTIVE_HEADING = re.compile(r"^Điều \d+\w*\.\s*(?:Hiệu lực thi hành|Điều khoản thi hành)")
_EFFECTIVE = re.compile(rf"có hiệu lực(?: thi hành)?(?: kể)? từ {_DATE_PHRASE}")
_ARTICLE_HEADING = re.compile(r"^Điều \d+\w*\.")

_DOC_TYPES = {
    "LUẬT": "Luật",
    "BỘ LUẬT": "Bộ luật",
    "NGHỊ QUYẾT": "Nghị quyết",
    "NGHỊ ĐỊNH": "Nghị định",
    "THÔNG TƯ": "Thông tư",
    "PHÁP LỆNH": "Pháp lệnh",
    "QUYẾT ĐỊNH": "Quyết định",
}
_TITLE_STOPS = {"QUỐC HỘI", "CHÍNH PHỦ", "QUYẾT NGHỊ:", "QUYẾT ĐỊNH:"}


def split_sections(lines: list[str]) -> DocumentSections:
    body_start = next((i for i, line in enumerate(lines) if _BODY_START.match(line)), None)
    if body_start is None:
        raise MetadataError("Không tìm thấy phần nội dung (Phần/Chương/Điều) trong văn bản")

    preamble_start = next(
        (i for i, line in enumerate(lines[:body_start]) if _PREAMBLE_START.match(line)),
        body_start,
    )
    footer_start = next(
        (i for i in range(body_start, len(lines)) if _FOOTER_START.match(lines[i])),
        len(lines),
    )
    return DocumentSections(
        header=lines[:preamble_start],
        preamble=lines[preamble_start:body_start],
        body=[line for line in lines[body_start:footer_start] if _has_text(line)],
        footer=lines[footer_start:],
    )


def extract_metadata(sections: DocumentSections) -> DocumentMetadata:
    so_hieu = _find_so_hieu(sections.header)
    doc_type, title = _find_type_and_title(sections.header)
    return DocumentMetadata(
        so_hieu=so_hieu,
        doc_type=doc_type,
        title=title,
        name=f"{doc_type} {title}",
        issuer=_find_issuer(sections.header),
        passed_date=_find_date(_PASSED, sections.footer + sections.body),
        effective_date=_find_effective_date(sections.body),
    )


def _find_so_hieu(header: list[str]) -> str:
    for line in header:
        if match := _SO_HIEU.search(line):
            return match.group(1).rstrip(".,;")
    raise MetadataError("Không tìm thấy số hiệu văn bản (dòng 'Luật số: ...')")


def _find_type_and_title(header: list[str]) -> tuple[str, str]:
    for i, line in enumerate(header):
        if line in _DOC_TYPES:
            title_lines: list[str] = []
            for candidate in header[i + 1 :]:
                if candidate in _TITLE_STOPS:
                    break
                if _has_text(candidate):
                    title_lines.append(candidate)
            title = " ".join(title_lines)
            if title.isupper():
                title = _sentence_case(title)
            return _DOC_TYPES[line], title
    raise MetadataError("Không xác định được loại văn bản (LUẬT, NGHỊ QUYẾT, ...)")


def _find_issuer(header: list[str]) -> str | None:
    first = next((line for line in header if _has_text(line)), None)
    return _sentence_case(first) if first and first.isupper() else first


def _find_effective_date(body: list[str]) -> date | None:
    for i, line in enumerate(body):
        if not _EFFECTIVE_HEADING.match(line):
            continue
        for candidate in body[i + 1 :]:
            if _ARTICLE_HEADING.match(candidate):
                break
            if candidate.startswith(("“", '"')):
                continue
            if match := _EFFECTIVE.search(candidate):
                return _to_date(match)
    return None


def _find_date(pattern: re.Pattern[str], lines: list[str]) -> date | None:
    for line in lines:
        if match := pattern.search(line):
            return _to_date(match)
    return None


def _to_date(match: re.Match[str]) -> date:
    day, month, year = (int(group) for group in match.groups()[-3:])
    return date(year, month, day)


def _sentence_case(text: str) -> str:
    lowered = text.lower()
    return lowered[:1].upper() + lowered[1:]


def _has_text(line: str) -> bool:
    return any(char.isalnum() for char in line)
