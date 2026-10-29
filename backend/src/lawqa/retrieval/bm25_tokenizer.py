import itertools
import re

from lawqa.ingestion.normalize import normalize_text

# Legal identifiers are kept whole so "45/2013/QH13" or "Điều 100" match exactly instead of
# dissolving into very common syllables ("điều", "2013", ...).
_DOCUMENT_NUMBER = re.compile(r"\b\d+/\d{4}/[^\W_]+(?:-[^\W_]+)*")
# A one-letter reference must not be the start of a word: "mục đích", "điều kiện" stay text.
_STRUCTURAL_REFERENCE = re.compile(
    r"\b(điều|khoản|điểm|chương|mục)\s+(\d+[a-zđ]?|[ivxlc]+|[a-zđ])(?![^\W_])"
)
_SEGMENT_BREAK = re.compile(r"[^\w\s]+|_")
_SYLLABLE = re.compile(r"[^\W_]+")
_REMOVED = " | "


def tokenize(text: str) -> list[str]:
    """Lowercased syllable unigrams and bigrams plus whole legal identifiers.

    Bigrams never span punctuation or a removed identifier.
    """
    text = normalize_text(text).lower()

    identifiers: list[str] = []

    def keep(match: re.Match[str]) -> str:
        identifiers.append(" ".join(match.group(0).split()))
        return _REMOVED

    text = _DOCUMENT_NUMBER.sub(keep, text)
    text = _STRUCTURAL_REFERENCE.sub(keep, text)

    tokens = identifiers
    for segment in _SEGMENT_BREAK.split(text):
        syllables = _SYLLABLE.findall(segment)
        tokens.extend(syllables)
        tokens.extend(f"{a} {b}" for a, b in itertools.pairwise(syllables))
    return tokens
