import re

from pydantic import BaseModel

_CITATION = re.compile(r"\s*\[(\d+(?:\s*[,;]\s*\d+)*)\]")


class CitationCheck(BaseModel):
    text: str
    cited: list[int]
    invalid: list[int]


def validate_citations(text: str, source_count: int) -> CitationCheck:
    """Drop citation numbers that do not point to one of the `source_count` sources."""
    cited: list[int] = []
    invalid: list[int] = []

    def clean(match: re.Match[str]) -> str:
        numbers = [int(n) for n in re.findall(r"\d+", match.group(1))]
        valid = [n for n in numbers if 1 <= n <= source_count]
        invalid.extend(n for n in numbers if not 1 <= n <= source_count)
        cited.extend(n for n in valid if n not in cited)
        if not valid:
            return ""
        leading = match.group(0)[: match.start(1) - match.start(0) - 1]
        return f"{leading}[{', '.join(str(n) for n in valid)}]"

    return CitationCheck(text=_CITATION.sub(clean, text), cited=cited, invalid=invalid)
