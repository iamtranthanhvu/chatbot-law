import json
from datetime import date
from pathlib import Path

import pytest

from lawqa.eval.dataset import EvalItem
from lawqa.eval.metrics.retrieval import RankedChunk
from lawqa.eval.report import render_markdown, write_report
from lawqa.eval.runner import run_retrieval_eval


def _item(item_id: str, persona: str, intent: str, dieu: str | None) -> EvalItem:
    return EvalItem.model_validate(
        {
            "id": item_id,
            "persona": persona,
            "intent": intent,
            "question": f"câu hỏi {item_id}",
            "reference_answer": "đáp án",
            "reference_citations": [{"dieu": dieu}] if dieu else [],
        }
    )


ITEMS = [
    _item("a", "layperson", "situation", "100"),
    _item("b", "professional", "lookup", "57"),
    _item("c", "layperson", "out_of_scope", None),
]


class FakeRetriever:
    """dense finds everything at rank 1; bm25 only finds article 57, at rank 2."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def search(
        self, texts: list[str], reference_date: date, *, mode: str
    ) -> list[RankedChunk]:
        self.calls.append((texts[0], mode))
        question = texts[0]
        if mode == "dense":
            dieu = "100" if question.endswith("a") else "57"
            return [RankedChunk(so_hieu="45/2013/QH13", article_number=dieu, clauses=[])]
        return [
            RankedChunk(so_hieu="45/2013/QH13", article_number="1", clauses=[]),
            RankedChunk(so_hieu="45/2013/QH13", article_number="57", clauses=[]),
        ]


async def test_runs_every_mode_and_aggregates_by_segment() -> None:
    retriever = FakeRetriever()

    report = await run_retrieval_eval(
        ITEMS, retriever, ["dense", "bm25"], date(2026, 10, 29), config={"top_k": 50}
    )

    assert report.items == 3
    assert report.evaluated == 2
    dense, bm25 = report.modes
    assert dense.mode == "dense" and dense.overall["recall@5"] == 1.0
    assert bm25.overall["recall@5"] == 0.5
    assert bm25.overall["mrr@10"] == pytest.approx(0.25)
    assert bm25.by_persona["professional"]["mrr@10"] == pytest.approx(0.5)
    assert bm25.by_persona["layperson"]["recall@10"] == 0.0
    assert set(bm25.by_intent) == {"situation", "lookup"}
    assert ("câu hỏi c", "dense") not in retriever.calls


async def test_report_is_written_as_json_and_markdown(tmp_path: Path) -> None:
    report = await run_retrieval_eval(
        ITEMS, FakeRetriever(), ["dense", "bm25"], date(2026, 10, 29), config={"top_k": 50}
    )

    json_path, md_path = write_report(report, tmp_path)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["config_hash"] == report.config_hash
    assert data["git_sha"]
    assert json_path.name.startswith("retrieval-") and md_path.suffix == ".md"
    markdown = md_path.read_text(encoding="utf-8")
    assert "| dense |" in markdown and "| bm25 |" in markdown
    assert "Theo persona" in markdown and "Theo intent" in markdown


async def test_markdown_lists_questions_missed_by_each_mode() -> None:
    report = await run_retrieval_eval(
        ITEMS, FakeRetriever(), ["bm25"], date(2026, 10, 29), config={}
    )

    markdown = render_markdown(report)

    assert "a — câu hỏi a" in markdown  # bm25 never finds article 100
