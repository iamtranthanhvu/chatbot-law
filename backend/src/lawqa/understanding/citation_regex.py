import re

from pydantic import BaseModel, ConfigDict

from lawqa.ingestion.normalize import normalize_text

# Keywords with or without diacritics; "điểm đ" keeps its đ, so diacritics are never stripped.
_DIEU = r"(?:điều|dieu)"
_KHOAN = r"(?:khoản|khoan)"
_DIEM = r"(?:điểm|diem)"
_REFERENCE = re.compile(
    rf"(?:{_DIEM}\s+(?P<diem>[a-zđ])\s*,?\s+)?"
    rf"(?:{_KHOAN}\s+(?P<khoan>\d+)\s*,?\s+)?"
    rf"{_DIEU}\s+(?P<dieu>[1-9]\d*[a-zđ]?)(?![^\W_])"
)
_DOCUMENT_NUMBER = re.compile(r"\b\d+/\d{4}/[a-zđ0-9]+(?:-[a-zđ0-9]+)*")


class CitationRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    dieu: str
    khoan: int | None = None
    diem: str | None = None
    so_hieu: str | None = None


def extract_citations(text: str) -> list[CitationRef]:
    """Article/clause/point references written in a question, in order of appearance."""
    lowered = normalize_text(text).lower()
    document = _DOCUMENT_NUMBER.search(lowered)
    so_hieu = document.group(0).upper() if document else None
    refs: list[CitationRef] = []
    for match in _REFERENCE.finditer(lowered):
        ref = CitationRef(
            dieu=match.group("dieu"),
            khoan=int(match.group("khoan")) if match.group("khoan") else None,
            diem=match.group("diem"),
            so_hieu=so_hieu,
        )
        if ref not in refs:
            refs.append(ref)
    return refs
