from collections.abc import Iterator
from pathlib import Path
from typing import cast

import docx
from docx.document import Document
from docx.oxml.ns import qn
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph
from lxml.etree import _Element


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
            yield Paragraph(cast(CT_P, child), document).text
        elif child.tag == qn("w:tbl"):
            yield from _iter_table_texts(Table(cast(CT_Tbl, child), document), document)
        elif child.tag == qn("w:sdt"):
            content = child.find(qn("w:sdtContent"))
            if content is not None:
                yield from _iter_block_texts(content, document)


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
