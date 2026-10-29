from collections.abc import Iterator
from pathlib import Path
from typing import cast

import docx
from docx.document import Document
from docx.oxml.ns import qn
from docx.oxml.table import CT_Tbl
from docx.table import Table
from lxml.etree import _Element

_MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
_TEXT = qn("w:t")
_LINE_BREAKS = {qn("w:br"), qn("w:cr")}
_TAB = qn("w:tab")
_NO_BREAK_HYPHEN = qn("w:noBreakHyphen")
# Not part of the visible paragraph text: deleted revisions, duplicate fallback renderings,
# text boxes (their own paragraphs) and paragraph/run property blocks.
_SKIPPED = {
    qn("w:del"),
    qn("w:moveFrom"),
    qn("w:txbxContent"),
    qn("w:pPr"),
    qn("w:rPr"),
    f"{_MC}Fallback",
}


def read_paragraphs(path: Path) -> list[str]:
    """Return raw text lines in document order, including text inside tables.

    Line breaks inside a paragraph become separate lines; no normalization is applied.
    """
    document = docx.Document(str(path))
    lines: list[str] = []
    for text in _iter_block_texts(document.element.body, document):
        lines.extend(text.split("\n"))
    return lines


def _iter_block_texts(container: _Element, document: Document) -> Iterator[str]:
    for child in container.iterchildren():
        if child.tag == qn("w:p"):
            yield "".join(_iter_paragraph_text(child))
        elif child.tag == qn("w:tbl"):
            yield from _iter_table_texts(Table(cast(CT_Tbl, child), document), document)
        elif child.tag == qn("w:sdt"):
            content = child.find(qn("w:sdtContent"))
            if content is not None:
                yield from _iter_block_texts(content, document)


def _iter_paragraph_text(element: _Element) -> Iterator[str]:
    """Collect visible text from every descendant run, whatever wraps it.

    python-docx's Paragraph.text only reads direct runs and hyperlinks, so text inside
    smart tags (Word wraps "Việt Nam" in them), custom XML, fields and tracked insertions
    is silently lost.
    """
    for child in element.iterchildren():
        tag = child.tag
        if not isinstance(tag, str) or tag in _SKIPPED:
            continue
        if tag == _TEXT:
            yield child.text or ""
        elif tag == _TAB:
            yield "\t"
        elif tag in _LINE_BREAKS:
            yield "\n"
        elif tag == _NO_BREAK_HYPHEN:
            yield "-"
        else:
            yield from _iter_paragraph_text(child)


def _iter_table_texts(table: Table, document: Document) -> Iterator[str]:
    # Merged cells repeat the same <w:tc>. Keep the elements themselves (not id()) so lxml
    # proxies stay alive; ids of collected proxies get reused and would drop real cells.
    seen: list[_Element] = []
    for row in table.rows:
        for cell in row.cells:
            if any(cell._tc is element for element in seen):
                continue
            seen.append(cell._tc)
            yield from _iter_block_texts(cell._tc, document)
