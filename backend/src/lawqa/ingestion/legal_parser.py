import hashlib
import re
from pathlib import Path

from lawqa.ingestion.docx_reader import read_paragraphs
from lawqa.ingestion.integrity import check_integrity
from lawqa.ingestion.metadata import extract_metadata, split_sections
from lawqa.ingestion.models import Article, Clause, Heading, ParsedDocument, ParseResult, Point
from lawqa.ingestion.normalize import normalize_lines

POINT_LETTERS = "abcdđeghiklmnopqrstuvxy"

_CHAPTER = re.compile(r"^(?:Chương|CHƯƠNG) ([IVXLC]+|\d+)\.?(?:\s+(.*))?$")
_SECTION = re.compile(r"^(?:Mục|MỤC) (\d+)\.?(?:\s+(.*))?$")
_ARTICLE = re.compile(r"^Điều (\d+[a-zđ]?)\.\s*(.*)$")
_CLAUSE = re.compile(r"^(\d+)\.\s")
_POINT = re.compile(rf"^([{POINT_LETTERS}])\)\s")


def parse_file(path: Path) -> ParsedDocument:
    """Read, normalize and parse a legal DOCX file; raises IntegrityError on structural problems."""
    sections = split_sections(normalize_lines(read_paragraphs(path)))
    structure = parse_body(sections.body)
    check_integrity(structure, sections.body)
    return ParsedDocument(
        metadata=extract_metadata(sections),
        preamble=sections.preamble,
        structure=structure,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        source_file=path.name,
    )


def parse_body(body: list[str]) -> ParseResult:
    return _BodyParser(body).parse()


class _BodyParser:
    def __init__(self, body: list[str]) -> None:
        self._body = body
        self._blocks: list[Article | Heading] = []
        self._warnings: list[str] = []
        self._orphans: list[str] = []
        self._chapter: Heading | None = None
        self._section: Heading | None = None
        self._article: Article | None = None
        self._clause: Clause | None = None
        self._point: Point | None = None

    def parse(self) -> ParseResult:
        i = 0
        while i < len(self._body):
            line = self._body[i]
            if match := _CHAPTER.match(line):
                i = self._open_heading("chuong", match, i)
            elif match := _SECTION.match(line):
                i = self._open_heading("muc", match, i)
            elif match := _ARTICLE.match(line):
                self._open_article(match, line)
                i += 1
            else:
                self._add_content(line)
                i += 1
        return ParseResult(blocks=self._blocks, warnings=self._warnings, orphans=self._orphans)

    def _open_heading(self, kind: str, match: re.Match[str], start: int) -> int:
        lines = [self._body[start]]
        title_parts = [match.group(2)] if match.group(2) else []
        i = start + 1
        # Heading titles are written in capitals and may wrap onto several lines.
        while i < len(self._body) and self._is_title_line(self._body[i]):
            lines.append(self._body[i])
            title_parts.append(self._body[i])
            i += 1
        heading = Heading(
            kind="chuong" if kind == "chuong" else "muc",
            number=match.group(1),
            title=" ".join(title_parts),
            lines=lines,
        )
        self._blocks.append(heading)
        self._article = self._clause = self._point = None
        if kind == "chuong":
            self._chapter, self._section = heading, None
        else:
            self._section = heading
        return i

    def _is_title_line(self, line: str) -> bool:
        return line.isupper() and not (
            _CHAPTER.match(line) or _SECTION.match(line) or _ARTICLE.match(line)
        )

    def _open_article(self, match: re.Match[str], line: str) -> None:
        self._article = Article(
            number=match.group(1),
            title=match.group(2),
            heading=line,
            chapter_number=self._chapter.number if self._chapter else None,
            chapter_title=self._chapter.title if self._chapter else None,
            section_number=self._section.number if self._section else None,
            section_title=self._section.title if self._section else None,
        )
        self._blocks.append(self._article)
        self._clause = self._point = None

    def _add_content(self, line: str) -> None:
        article = self._article
        if article is None:
            self._orphans.append(line)
            return

        if clause_match := _CLAUSE.match(line):
            number = int(clause_match.group(1))
            last = article.clauses[-1].number if article.clauses else 0
            # Forward gaps exist in official texts (repealed or mistyped clauses): accept them
            # with a warning. A repeated or backward number is ordinary text that starts with
            # a number.
            if number > last:
                if number != last + 1:
                    self._warn(article, f"nhảy từ khoản {last} sang khoản {number}")
                self._clause = Clause(number=number, lines=[line])
                article.clauses.append(self._clause)
                self._point = None
                return
            self._warn(article, f"khoản {number} không tăng dần, giữ làm nội dung: {line[:60]}")

        elif point_match := _POINT.match(line):
            owner = self._clause.points if self._clause else article.points
            letter = point_match.group(1)
            last_index = POINT_LETTERS.index(owner[-1].letter) if owner else -1
            index = POINT_LETTERS.index(letter)
            if index > last_index and (owner or letter == "a"):
                if index != last_index + 1:
                    previous = owner[-1].letter
                    self._warn(
                        article, f"nhảy từ điểm {previous}) sang điểm {letter}) — {line[:60]}"
                    )
                self._point = Point(letter=letter, lines=[line])
                owner.append(self._point)
                return
            self._warn(article, f"điểm {letter}) không đúng thứ tự, giữ làm nội dung: {line[:60]}")

        self._append_continuation(article, line)

    def _append_continuation(self, article: Article, line: str) -> None:
        if self._point is not None:
            self._point.lines.append(line)
        elif self._clause is not None:
            self._clause.lines.append(line)
        else:
            article.intro.append(line)

    def _warn(self, article: Article, problem: str) -> None:
        self._warnings.append(f"Điều {article.number}: {problem}")
