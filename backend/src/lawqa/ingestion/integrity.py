import re

from lawqa.ingestion.models import ParseResult

_ARTICLE_NUMBER = re.compile(r"^(\d+)([a-zđ]?)$")


class IntegrityError(ValueError):
    def __init__(self, issues: list[str]) -> None:
        self.issues = issues
        super().__init__("Văn bản không toàn vẹn:\n- " + "\n- ".join(issues))


def check_integrity(result: ParseResult, body: list[str]) -> None:
    issues: list[str] = []

    issues.extend(f"Đoạn văn nằm ngoài mọi Điều: {line[:80]}" for line in result.orphans)
    if not result.articles:
        issues.append("Không tìm thấy Điều nào")
    issues.extend(_article_numbering_issues(result))
    if not result.orphans:
        issues.extend(_reconstruction_issues(result, body))

    if issues:
        raise IntegrityError(issues)


def _article_numbering_issues(result: ParseResult) -> list[str]:
    issues: list[str] = []
    seen: set[str] = set()
    expected = 1
    for article in result.articles:
        if article.number in seen:
            issues.append(f"Điều {article.number} bị trùng")
        seen.add(article.number)

        match = _ARTICLE_NUMBER.match(article.number)
        if match is None:
            issues.append(f"Số Điều không hợp lệ: {article.number}")
            continue
        number, suffix = int(match.group(1)), match.group(2)
        if suffix:
            continue
        if number != expected:
            missing = ", ".join(f"Điều {n}" for n in range(expected, number)) or "-"
            issues.append(f"Số Điều không liên tục trước Điều {number} (thiếu: {missing})")
        expected = number + 1
    return issues


def _reconstruction_issues(result: ParseResult, body: list[str]) -> list[str]:
    rebuilt = result.all_lines()
    if rebuilt == body:
        return []
    index = next(
        (i for i, (a, b) in enumerate(zip(rebuilt, body, strict=False)) if a != b),
        min(len(rebuilt), len(body)),
    )
    found = rebuilt[index][:80] if index < len(rebuilt) else "<hết>"
    original = body[index][:80] if index < len(body) else "<hết>"
    return [f"Nội dung sau khi tách không khớp văn bản tại dòng {index}: '{found}' ≠ '{original}'"]
