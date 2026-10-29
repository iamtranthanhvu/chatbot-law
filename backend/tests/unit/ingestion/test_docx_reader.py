from pathlib import Path

import docx

from lawqa.ingestion.docx_reader import read_paragraphs


def _build_docx(path: Path) -> Path:
    document = docx.Document()
    table = document.add_table(rows=1, cols=2)
    left = table.cell(0, 0).paragraphs[0]
    left.add_run("QUỐC HỘI")
    left.add_run().add_break()
    left.add_run("-------")
    table.cell(0, 1).paragraphs[0].add_run("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM")
    document.add_paragraph("LUẬT")
    document.add_paragraph("Điều 1. Phạm vi điều chỉnh")
    document.add_paragraph("")
    document.add_paragraph("Luật này quy định về chế độ sở hữu đất đai.")
    document.save(str(path))
    return path


def test_reads_tables_and_paragraphs_in_document_order(tmp_path: Path) -> None:
    lines = read_paragraphs(_build_docx(tmp_path / "doc.docx"))

    assert lines == [
        "QUỐC HỘI",
        "-------",
        "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM",
        "LUẬT",
        "Điều 1. Phạm vi điều chỉnh",
        "",
        "Luật này quy định về chế độ sở hữu đất đai.",
    ]


def test_reads_every_cell_of_a_large_table(tmp_path: Path) -> None:
    document = docx.Document()
    table = document.add_table(rows=6, cols=4)
    expected = []
    for r in range(6):
        for c in range(4):
            text = f"ô {r}-{c}"
            table.cell(r, c).paragraphs[0].add_run(text)
            expected.append(text)
    path = tmp_path / "large.docx"
    document.save(str(path))

    assert read_paragraphs(path) == expected


def test_merged_cells_are_read_once(tmp_path: Path) -> None:
    document = docx.Document()
    table = document.add_table(rows=1, cols=2)
    merged = table.cell(0, 0).merge(table.cell(0, 1))
    merged.paragraphs[0].add_run("CHỦ TỊCH QUỐC HỘI")
    path = tmp_path / "merged.docx"
    document.save(str(path))

    assert read_paragraphs(path) == ["CHỦ TỊCH QUỐC HỘI"]
