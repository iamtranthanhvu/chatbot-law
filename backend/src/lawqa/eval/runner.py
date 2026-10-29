import hashlib
import json
import subprocess
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from statistics import fmean
from typing import Any, Protocol

from pydantic import BaseModel

from lawqa.eval.dataset import EvalItem
from lawqa.eval.metrics.retrieval import ChunkLike, retrieval_metrics


class ModeSearch(Protocol):
    async def search(
        self, texts: list[str], reference_date: date, *, mode: Any
    ) -> Sequence[ChunkLike]: ...


class ModeResult(BaseModel):
    mode: str
    overall: dict[str, float]
    by_persona: dict[str, dict[str, float]]
    by_intent: dict[str, dict[str, float]]
    per_item: dict[str, dict[str, float]]


class RetrievalReport(BaseModel):
    kind: str = "retrieval"
    dataset: str
    items: int
    evaluated: int
    reference_date: date
    modes: list[ModeResult]
    questions: dict[str, str]
    config: dict[str, Any]
    config_hash: str
    git_sha: str
    created_at: datetime


async def run_retrieval_eval(
    items: list[EvalItem],
    retriever: ModeSearch,
    modes: list[str],
    reference_date: date,
    *,
    config: dict[str, Any],
    dataset: str = "",
) -> RetrievalReport:
    evaluated = [item for item in items if item.has_references]
    results = []
    for mode in modes:
        per_item: dict[str, dict[str, float]] = {}
        for item in evaluated:
            ranked = await retriever.search([item.question], reference_date, mode=mode)
            metrics = retrieval_metrics(ranked, item.reference_citations)
            if metrics is not None:
                per_item[item.id] = metrics
        results.append(
            ModeResult(
                mode=mode,
                overall=_mean(per_item.values()),
                by_persona=_grouped(evaluated, per_item, lambda i: i.persona),
                by_intent=_grouped(evaluated, per_item, lambda i: i.intent),
                per_item=per_item,
            )
        )
    return RetrievalReport(
        dataset=dataset,
        items=len(items),
        evaluated=len(evaluated),
        reference_date=reference_date,
        modes=results,
        questions={item.id: item.question for item in evaluated},
        config=config,
        config_hash=config_hash(config),
        git_sha=git_sha(),
        created_at=datetime.now(UTC),
    )


def _mean(rows: Any) -> dict[str, float]:
    rows = list(rows)
    if not rows:
        return {}
    return {key: fmean(row[key] for row in rows) for key in rows[0]}


def _grouped(
    items: list[EvalItem], per_item: dict[str, dict[str, float]], key: Any
) -> dict[str, dict[str, float]]:
    groups: dict[str, list[dict[str, float]]] = defaultdict(list)
    for item in items:
        if item.id in per_item:
            groups[key(item)].append(per_item[item.id])
    return {name: _mean(rows) for name, rows in sorted(groups.items())}


def config_hash(config: dict[str, Any]) -> str:
    payload = json.dumps(config, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def git_sha() -> str:
    repo = Path(__file__).resolve().parents[4]
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return f"{sha}-dirty" if dirty else sha
