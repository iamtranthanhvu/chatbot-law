import unicodedata
from collections.abc import Iterable

_TRANSLATION = str.maketrans(
    {
        " ": " ",
        " ": " ",
        " ": " ",
        " ": " ",
        " ": " ",
        "​": None,
        "‌": None,
        "‍": None,
        "﻿": None,
        "­": None,
        # Icelandic eth is a frequent look-alike for Vietnamese Đ/đ in legal documents.
        "Ð": "Đ",
        "ð": "đ",
    }
)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text).translate(_TRANSLATION)
    return " ".join(text.split())


def normalize_lines(lines: Iterable[str]) -> list[str]:
    return [normalized for line in lines if (normalized := normalize_text(line))]
