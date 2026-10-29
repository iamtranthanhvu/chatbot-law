from typing import Literal

from pydantic import BaseModel, Field

from lawqa.ingestion.metadata import DocumentMetadata


class Point(BaseModel):
    letter: str
    lines: list[str]

    @property
    def path_segment(self) -> str:
        return f"diem-{self.letter}"


class Clause(BaseModel):
    number: int
    lines: list[str]
    points: list[Point] = Field(default_factory=list)

    @property
    def path_segment(self) -> str:
        return f"khoan-{self.number}"

    def all_lines(self) -> list[str]:
        return [*self.lines, *(line for point in self.points for line in point.lines)]


class Article(BaseModel):
    block: Literal["article"] = "article"
    number: str
    title: str
    heading: str
    intro: list[str] = Field(default_factory=list)
    points: list[Point] = Field(default_factory=list)
    clauses: list[Clause] = Field(default_factory=list)
    chapter_number: str | None = None
    chapter_title: str | None = None
    section_number: str | None = None
    section_title: str | None = None

    @property
    def path(self) -> str:
        return f"dieu-{self.number}"

    def all_lines(self) -> list[str]:
        return [
            self.heading,
            *self.intro,
            *(line for point in self.points for line in point.lines),
            *(line for clause in self.clauses for line in clause.all_lines()),
        ]


class Heading(BaseModel):
    block: Literal["heading"] = "heading"
    kind: Literal["phan", "chuong", "muc"]
    number: str
    title: str
    lines: list[str]


class ParseResult(BaseModel):
    blocks: list[Article | Heading]
    warnings: list[str] = Field(default_factory=list)
    orphans: list[str] = Field(default_factory=list)

    @property
    def articles(self) -> list[Article]:
        return [block for block in self.blocks if isinstance(block, Article)]

    @property
    def chapters(self) -> list[Heading]:
        return [b for b in self.blocks if isinstance(b, Heading) and b.kind == "chuong"]

    def all_lines(self) -> list[str]:
        lines: list[str] = []
        for block in self.blocks:
            lines.extend(block.all_lines() if isinstance(block, Article) else block.lines)
        return lines


class ParsedDocument(BaseModel):
    metadata: DocumentMetadata
    preamble: list[str]
    structure: ParseResult
    sha256: str
    source_file: str
