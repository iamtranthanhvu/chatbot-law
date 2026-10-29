from collections import defaultdict
from collections.abc import AsyncIterator, Callable
from datetime import UTC, date, datetime
from statistics import fmean
from typing import Any, Protocol

from pydantic import BaseModel, Field

from lawqa.eval.dataset import EvalItem
from lawqa.eval.judge import Judge, JudgeScores
from lawqa.eval.metrics.generation import citation_scores, is_refusal, percentile
from lawqa.eval.runner import config_hash, git_sha
from lawqa.pipelines.base import DoneEvent, ErrorEvent, PipelineEvent, Query, Source, SourcesEvent


class AnsweringPipeline(Protocol):
    name: str

    def answer(self, query: Query) -> AsyncIterator[PipelineEvent]: ...


class ItemResult(BaseModel):
    id: str
    persona: str
    intent: str
    question: str
    in_scope: bool
    answer: str = ""
    citations: list[int] = Field(default_factory=list)
    invalid_citations: list[int] = Field(default_factory=list)
    cited_articles: list[str] = Field(default_factory=list)
    refused: bool = False
    error: str | None = None
    latency_ms: dict[str, int] = Field(default_factory=dict)
    citation_precision: float | None = None
    citation_recall: float | None = None
    scores: JudgeScores | None = None
    judge_error: str | None = None


class GenerationReport(BaseModel):
    kind: str = "generation"
    dataset: str
    items: int
    reference_date: date
    pipeline: str
    judge_model: str
    overall: dict[str, float]
    by_persona: dict[str, dict[str, float]]
    by_intent: dict[str, dict[str, float]]
    per_item: dict[str, ItemResult]
    config: dict[str, Any]
    config_hash: str
    git_sha: str
    created_at: datetime


async def run_generation_eval(
    items: list[EvalItem],
    pipeline: AnsweringPipeline,
    judge: Judge,
    reference_date: date,
    *,
    config: dict[str, Any],
    dataset: str = "",
) -> GenerationReport:
    """Answer every question first, then judge them, so only one model is loaded at a time."""
    results: list[ItemResult] = []
    sources_by_id: dict[str, list[Source]] = {}
    for item in items:
        result, sources = await _answer(item, pipeline, reference_date)
        results.append(result)
        sources_by_id[item.id] = sources

    by_id = {item.id: item for item in items}
    for result in results:
        if result.in_scope and not result.error and not result.refused:
            result.scores, result.judge_error = await judge.score(
                by_id[result.id], result.answer, sources_by_id[result.id]
            )

    return GenerationReport(
        dataset=dataset,
        items=len(items),
        reference_date=reference_date,
        pipeline=pipeline.name,
        judge_model=judge.model,
        overall=_aggregate(results),
        by_persona=_grouped(results, lambda r: r.persona),
        by_intent=_grouped(results, lambda r: r.intent),
        per_item={result.id: result for result in results},
        config=config,
        config_hash=config_hash(config),
        git_sha=git_sha(),
        created_at=datetime.now(UTC),
    )


async def _answer(
    item: EvalItem, pipeline: AnsweringPipeline, reference_date: date
) -> tuple[ItemResult, list[Source]]:
    result = ItemResult(
        id=item.id,
        persona=item.persona,
        intent=item.intent,
        question=item.question,
        in_scope=item.intent != "out_of_scope",
    )
    sources: list[Source] = []
    async for event in pipeline.answer(Query(text=item.question, reference_date=reference_date)):
        if isinstance(event, SourcesEvent):
            sources = event.sources
        elif isinstance(event, ErrorEvent):
            result.error = event.code
        elif isinstance(event, DoneEvent):
            result.answer = event.answer
            result.citations = event.citations
            result.invalid_citations = event.invalid_citations
            result.latency_ms = event.latency_ms
            result.refused = is_refusal(event.answer)
    result.cited_articles = [f"Điều {s.dieu}" for s in sources if s.n in result.citations]
    if result.in_scope and not result.error:
        scores = citation_scores(result.citations, sources, item.reference_citations)
        result.citation_precision = scores["citation_precision"]
        result.citation_recall = scores["citation_recall"]
    return result, sources


def _aggregate(results: list[ItemResult]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    if results:
        metrics["error_rate"] = sum(1 for r in results if r.error) / len(results)
    answered = [r for r in results if not r.error]
    in_scope = [r for r in answered if r.in_scope]
    out_of_scope = [r for r in answered if not r.in_scope]
    judged = [r for r in in_scope if r.scores is not None]

    def mean(name: str, rows: list[ItemResult], value: Callable[[ItemResult], float]) -> None:
        if rows:
            metrics[name] = fmean(value(r) for r in rows)

    mean("refusal_accuracy", out_of_scope, lambda r: float(r.refused))
    mean("false_refusal_rate", in_scope, lambda r: float(r.refused))
    mean("citation_precision", in_scope, lambda r: r.citation_precision or 0.0)
    mean("citation_recall", in_scope, lambda r: r.citation_recall or 0.0)
    mean("invalid_citation_rate", answered, lambda r: float(bool(r.invalid_citations)))
    mean("faithfulness", judged, lambda r: r.scores.faithfulness if r.scores else 0.0)
    mean("correctness", judged, lambda r: r.scores.correctness if r.scores else 0.0)
    laypeople = [r for r in judged if r.persona == "layperson"]
    mean("clarity_layperson", laypeople, lambda r: r.scores.clarity if r.scores else 0.0)
    if in_scope:
        metrics["judge_error_rate"] = sum(1 for r in in_scope if r.judge_error) / len(in_scope)

    for stage in ("retrieve", "ttft", "total"):
        values = [r.latency_ms[stage] for r in answered if stage in r.latency_ms]
        if values:
            metrics[f"latency_{stage}_p50"] = percentile(values, 50)
            metrics[f"latency_{stage}_p95"] = percentile(values, 95)
    return metrics


def _grouped(
    results: list[ItemResult], key: Callable[[ItemResult], str]
) -> dict[str, dict[str, float]]:
    groups: dict[str, list[ItemResult]] = defaultdict(list)
    for result in results:
        groups[key(result)].append(result)
    return {name: _aggregate(rows) for name, rows in sorted(groups.items())}
