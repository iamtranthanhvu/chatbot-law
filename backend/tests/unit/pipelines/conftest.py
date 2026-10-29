from datetime import date

from lawqa.retrieval.types import RetrievedChunk


class WordCounter:
    def count(self, text: str) -> int:
        return len(text.split())


def make_chunk(
    article: str,
    text: str,
    *,
    ordinal: int = 0,
    score: float = 0.5,
    title: str = "Tiêu đề",
    clauses: list[int] | None = None,
) -> RetrievedChunk:
    path = f"dieu-{article}" if ordinal == 0 else f"dieu-{article}/p{ordinal + 1}"
    return RetrievedChunk(
        chunk_id=f"id-{article}-{ordinal}",
        document_id="doc",
        so_hieu="45/2013/QH13",
        path=path,
        ordinal=ordinal,
        article_number=article,
        article_title=title,
        chapter_number="1",
        chapter_title="QUY ĐỊNH CHUNG",
        section_number=None,
        section_title=None,
        clauses=clauses or [],
        points=[],
        text=text,
        context_text=f"Luật Đất đai (45/2013/QH13) > Điều {article}. {title}\n{text}",
        token_count=len(text.split()),
        valid_from=date(2014, 7, 1),
        valid_to=None,
        score=score,
        stage="fused",
    )
