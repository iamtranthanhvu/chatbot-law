import re

from pydantic import BaseModel

_GROUP = r"\[\d+(?:\s*[,;]\s*\d+)*\]"
# A run of adjacent citation groups such as "[1], [3]" or "[2][5]" is cleaned as one unit so
# removing invalid groups does not leave stray separators ("[1],,,").
_RUN = re.compile(rf"\s*{_GROUP}(?:\s*[,;]?\s*{_GROUP})*")
_SEPARATOR = re.compile(rf"{_GROUP}(\s*[,;]?\s*){_GROUP}")


class CitationCheck(BaseModel):
    text: str
    cited: list[int]
    invalid: list[int]


def validate_citations(text: str, source_count: int) -> CitationCheck:
    """Drop citation numbers that do not point to one of the `source_count` sources."""
    cited: list[int] = []
    invalid: list[int] = []

    def clean(match: re.Match[str]) -> str:
        run = match.group(0)
        kept: list[str] = []
        for group in re.findall(_GROUP, run):
            numbers = [int(n) for n in re.findall(r"\d+", group)]
            valid = [n for n in numbers if 1 <= n <= source_count]
            invalid.extend(n for n in numbers if not 1 <= n <= source_count)
            cited.extend(n for n in valid if n not in cited)
            if valid:
                kept.append(f"[{', '.join(str(n) for n in valid)}]")
        if not kept:
            return ""
        separator = _SEPARATOR.search(run)
        leading = run[: len(run) - len(run.lstrip())]
        return leading + (separator.group(1) if separator else "").join(kept)

    return CitationCheck(text=_RUN.sub(clean, text), cited=cited, invalid=invalid)
