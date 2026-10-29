import json
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from lawqa.eval.compare import compare_reports
from lawqa.eval.dataset import Citation, EvalItem
from lawqa.eval.generation_runner import run_generation_eval
from lawqa.eval.judge import Judge, JudgeConfigError, check_judge_config
from lawqa.eval.metrics.generation import (
    answer_structure,
    citation_scores,
    is_refusal,
    percentile,
)
from lawqa.eval.report import write_report
from lawqa.generation.llm_client import Message
from lawqa.pipelines.base import (
    DoneEvent,
    ErrorEvent,
    MetaEvent,
    PipelineEvent,
    Query,
    Source,
    SourcesEvent,
)


def _source(n: int, dieu: str, khoan: list[int] | None = None) -> Source:
    return Source(
        n=n,
        chunk_ids=[f"c{n}"],
        so_hieu="45/2013/QH13",
        dieu=dieu,
        khoan=khoan or [],
        title="t",
        snippet="s",
        score=0.5,
        context=f"[{n}] Điều {dieu} nội dung",
    )


def _item(item_id: str, persona: str, intent: str, dieu: str | None) -> EvalItem:
    return EvalItem.model_validate(
        {
            "id": item_id,
            "persona": persona,
            "intent": intent,
            "question": f"q-{item_id}",
            "reference_answer": "đáp án mẫu",
            "reference_citations": [{"dieu": dieu}] if dieu else [],
        }
    )


def test_citation_precision_and_recall() -> None:
    sources = [_source(1, "57", [1]), _source(2, "12", [3]), _source(3, "99")]
    gold = _item("x", "layperson", "situation", "57").reference_citations

    scores = citation_scores(cited=[1, 3], sources=sources, gold=gold)

    assert scores == {"citation_precision": 0.5, "citation_recall": 1.0}


def test_no_citations_means_zero_precision_and_recall() -> None:
    gold = _item("x", "layperson", "situation", "57").reference_citations

    assert citation_scores([], [_source(1, "57")], gold) == {
        "citation_precision": 0.0,
        "citation_recall": 0.0,
    }


def test_refusal_detection() -> None:
    assert is_refusal("Không tìm thấy căn cứ trong dữ liệu hiện có.")
    assert not is_refusal("Người sử dụng đất được chuyển nhượng khi có Giấy chứng nhận [1].")


def test_situation_answers_need_a_conclusion_and_a_legal_basis() -> None:
    good = "**Kết luận:** Không được [1].\n**Căn cứ pháp lý:**\n- Điều 57 [1]"

    assert answer_structure("situation", good, [], []) is True
    assert answer_structure("situation", "Không được xây nhà [1].", [], []) is False


ARTICLE_100 = _source(1, "100").model_copy(
    update={
        "context": "[1] Luật Đất đai (45/2013/QH13) — Điều 100. Cấp Giấy chứng nhận\n"
        "1. Hộ gia đình, cá nhân đang sử dụng đất ổn định mà có một trong các loại giấy tờ "
        "sau đây thì được cấp Giấy chứng nhận"
    }
)


def test_lookup_answers_must_quote_the_article_asked_about() -> None:
    quoted = (
        'Khoản 1 Điều 100 quy định: "Hộ gia đình, cá nhân đang sử dụng đất ổn định mà có '
        'một trong các loại giấy tờ sau đây thì được cấp" [1].'
    )
    paraphrased = "Ai có giấy tờ về đất thì được cấp sổ [1]."

    assert answer_structure("lookup", quoted, [ARTICLE_100], [Citation(dieu="100")]) is True
    assert answer_structure("lookup", paraphrased, [ARTICLE_100], [Citation(dieu="100")]) is False
    assert answer_structure("lookup", quoted, [ARTICLE_100], [Citation(dieu="101")]) is False


def test_other_intents_have_no_structure_check() -> None:
    assert answer_structure("topic_search", "x", [], []) is None


def test_percentile() -> None:
    assert percentile([100, 200, 300, 400], 50) == 250
    assert percentile([100, 200, 300, 400], 95) == pytest.approx(385)


class FakeJudgeLLM:
    model = "judge-model"

    def __init__(self, replies: list[str]) -> None:
        self.replies = replies
        self.calls: list[list[Message]] = []

    async def complete(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        self.calls.append(messages)
        return self.replies.pop(0) if self.replies else "không phải JSON"


GOOD = json.dumps({"faithfulness": 0.9, "correctness": 0.8, "clarity": 0.7, "reason": "ổn"})


async def test_judge_parses_scores_and_retries_once_on_bad_json() -> None:
    llm = FakeJudgeLLM(["{hỏng", GOOD])

    scores, error = await Judge(llm).score(
        _item("a", "layperson", "situation", "57"), "câu trả lời", [_source(1, "57")]
    )

    assert error is None and scores is not None
    assert scores.faithfulness == 0.9 and scores.clarity == 0.7
    assert len(llm.calls) == 2
    assert "đáp án mẫu" in llm.calls[0][1]["content"]


async def test_judge_gives_up_after_two_bad_replies() -> None:
    scores, error = await Judge(FakeJudgeLLM(["{x", "{y"])).score(
        _item("a", "layperson", "situation", "57"), "câu trả lời", [_source(1, "57")]
    )

    assert scores is None and error is not None


def test_judging_the_model_with_itself_needs_explicit_permission() -> None:
    same = {"base_url": "http://ollama:11434", "model": "qwen3:4b-instruct"}

    with pytest.raises(JudgeConfigError):
        check_judge_config(generator=same, judge=same, allow_self_judge=False)
    check_judge_config(generator=same, judge=same, allow_self_judge=True)
    check_judge_config(generator=same, judge={**same, "model": "qwen3:8b"}, allow_self_judge=False)


class FakePipeline:
    name = "hybrid"

    def __init__(self, answers: dict[str, list[PipelineEvent]]) -> None:
        self.answers = answers

    async def answer(self, query: Query) -> AsyncIterator[PipelineEvent]:
        for event in self.answers[query.text]:
            yield event


def _done(answer: str, cited: list[int], invalid: list[int] | None = None) -> DoneEvent:
    return DoneEvent(
        answer=answer,
        citations=cited,
        invalid_citations=invalid or [],
        model="gen",
        latency_ms={"retrieve": 100, "ttft": 1000, "total": 2000},
    )


ITEMS = [
    _item("a", "layperson", "situation", "57"),
    _item("b", "professional", "lookup", "100"),
    _item("o", "layperson", "out_of_scope", None),
    _item("e", "professional", "topic_search", "12"),
]


def _pipeline() -> FakePipeline:
    meta = MetaEvent(query_id="q", pipeline="hybrid")
    return FakePipeline(
        {
            "q-a": [
                meta.model_copy(update={"intent": "situation"}),
                SourcesEvent(sources=[_source(1, "57")]),
                _done("Phải xin phép [1].", [1]),
            ],
            "q-b": [
                meta,
                SourcesEvent(sources=[_source(1, "101")]),
                _done("Không tìm thấy căn cứ trong dữ liệu hiện có.", []),
            ],
            "q-o": [
                meta,
                SourcesEvent(sources=[_source(1, "64")]),
                _done("Không tìm thấy căn cứ trong dữ liệu hiện có.", []),
            ],
            "q-e": [meta, ErrorEvent(code="LLM_TIMEOUT", message="quá lâu")],
        }
    )


async def test_generation_eval_aggregates_code_and_judge_metrics(tmp_path: Path) -> None:
    judge = Judge(FakeJudgeLLM([GOOD]))

    report = await run_generation_eval(
        ITEMS, _pipeline(), judge, date(2026, 10, 29), config={"model": "gen"}
    )

    assert report.kind == "generation"
    overall = report.overall
    assert overall["error_rate"] == 0.25
    assert overall["refusal_accuracy"] == 1.0  # the out-of-scope question was refused
    assert overall["false_refusal_rate"] == pytest.approx(1 / 2)  # b refused although in scope
    assert overall["citation_recall"] == pytest.approx(0.5)  # a: 1.0, b: 0.0
    assert overall["faithfulness"] == 0.9  # only a was judged
    assert overall["latency_total_p50"] == 2000
    assert report.per_item["e"].error == "LLM_TIMEOUT"
    assert report.per_item["a"].predicted_intent == "situation"
    assert overall["structure_ok"] == 0.0  # a has no "Kết luận" section
    assert set(report.by_persona) == {"layperson", "professional"}

    json_path, md_path = write_report(report, tmp_path)
    assert json_path.name.startswith("generation-")
    assert "faithfulness" in md_path.read_text(encoding="utf-8")


async def test_compare_puts_runs_side_by_side(tmp_path: Path) -> None:
    first = await run_generation_eval(
        ITEMS, _pipeline(), Judge(FakeJudgeLLM([GOOD])), date(2026, 10, 29), config={"m": 1}
    )
    second = await run_generation_eval(
        ITEMS, _pipeline(), Judge(FakeJudgeLLM([GOOD])), date(2026, 10, 29), config={"m": 2}
    )
    paths = [write_report(first, tmp_path / "1")[0], write_report(second, tmp_path / "2")[0]]

    markdown = compare_reports(paths)

    assert markdown.count(first.config_hash) == 1 and second.config_hash in markdown
    assert "| faithfulness |" in markdown
