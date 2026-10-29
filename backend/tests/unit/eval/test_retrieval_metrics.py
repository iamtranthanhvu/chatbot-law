import json
import math
from pathlib import Path

import pytest

from lawqa.eval.dataset import Citation, EvalItem, load_dataset
from lawqa.eval.metrics.retrieval import RankedChunk, retrieval_metrics

SEED = Path(__file__).resolve().parents[4] / "eval" / "datasets" / "seed.jsonl"


def _chunk(dieu: str, clauses: list[int] | None = None) -> RankedChunk:
    return RankedChunk(so_hieu="45/2013/QH13", article_number=dieu, clauses=clauses or [])


def test_seed_dataset_loads_and_ids_are_unique() -> None:
    items = load_dataset(SEED)

    assert len(items) >= 30
    assert len({item.id for item in items}) == len(items)
    assert {item.persona for item in items} == {"layperson", "professional"}


def test_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    row = {
        "id": "x",
        "persona": "layperson",
        "intent": "lookup",
        "question": "q",
        "reference_citations": [],
        "reference_answer": "a",
    }
    path = tmp_path / "dup.jsonl"
    path.write_text("\n".join([json.dumps(row), json.dumps(row)]), encoding="utf-8")

    with pytest.raises(ValueError, match="x"):
        load_dataset(path)


def test_perfect_ranking() -> None:
    gold = [Citation(dieu="100"), Citation(dieu="101")]

    metrics = retrieval_metrics([_chunk("100"), _chunk("101"), _chunk("5")], gold)

    assert metrics == {"recall@5": 1.0, "recall@10": 1.0, "mrr@10": 1.0, "ndcg@10": 1.0}


def test_hand_computed_example() -> None:
    gold = [Citation(dieu="57", khoan=1), Citation(dieu="12", khoan=3)]
    ranked = [
        _chunk("57", [2]),  # right article, wrong clause → not relevant
        _chunk("9"),
        _chunk("57", [1, 2]),  # rank 3: relevant to gold #1
        _chunk("57", [1]),  # same gold again → no extra gain
        _chunk("1"),
        _chunk("2"),
        _chunk("12", [1, 2, 3]),  # rank 7: relevant to gold #2
    ]

    metrics = retrieval_metrics(ranked, gold)

    assert metrics["recall@5"] == 0.5
    assert metrics["recall@10"] == 1.0
    assert metrics["mrr@10"] == pytest.approx(1 / 3)
    dcg = 1 / math.log2(3 + 1) + 1 / math.log2(7 + 1)
    ideal = 1 / math.log2(2) + 1 / math.log2(3)
    assert metrics["ndcg@10"] == pytest.approx(dcg / ideal)


def test_article_without_clauses_counts_for_any_clause_citation() -> None:
    metrics = retrieval_metrics([_chunk("113")], [Citation(dieu="113", khoan=1)])

    assert metrics["recall@5"] == 1.0


def test_nothing_relevant_in_the_top_ten() -> None:
    ranked = [_chunk(str(n)) for n in range(1, 11)] + [_chunk("100")]

    metrics = retrieval_metrics(ranked, [Citation(dieu="100")])

    assert metrics == {"recall@5": 0.0, "recall@10": 0.0, "mrr@10": 0.0, "ndcg@10": 0.0}


def test_items_without_references_have_no_retrieval_metrics() -> None:
    item = EvalItem(
        id="o1",
        persona="layperson",
        intent="out_of_scope",
        question="Vượt đèn đỏ phạt bao nhiêu?",
        reference_citations=[],
        reference_answer="Ngoài phạm vi.",
    )

    assert item.has_references is False
    assert retrieval_metrics([_chunk("1")], item.reference_citations) is None
