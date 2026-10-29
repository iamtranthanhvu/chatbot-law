import json
from pathlib import Path
from typing import Any

from lawqa.eval.report import GENERATION_METRICS, METRICS


def compare_reports(paths: list[Path]) -> str:
    """Side-by-side overall metrics of several report JSON files, grouped by report kind."""
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    lines = ["# So sánh các lần đánh giá", ""]
    for kind in ("retrieval", "generation"):
        runs = [r for r in reports if r.get("kind") == kind]
        if not runs:
            continue
        columns, values = _columns(kind, runs)
        lines += [f"## {kind}", "", "| metric | " + " | ".join(columns) + " |"]
        lines.append("|" + "---|" * (len(columns) + 1))
        metrics = METRICS if kind == "retrieval" else GENERATION_METRICS
        for metric in metrics:
            cells = [f"{v[metric]:.3f}" if metric in v else "—" for v in values]
            if any(cell != "—" for cell in cells):
                lines.append(f"| {metric} | " + " | ".join(cells) + " |")
        lines.append("")
    return "\n".join(lines)


def _columns(kind: str, runs: list[dict[str, Any]]) -> tuple[list[str], list[dict[str, float]]]:
    columns: list[str] = []
    values: list[dict[str, float]] = []
    for run in runs:
        label = f"{run['git_sha']} · {run['config_hash']} · {run['created_at'][:16]}"
        if kind == "retrieval":
            for mode in run["modes"]:
                columns.append(f"{mode['mode']} ({label})")
                values.append(mode["overall"])
        else:
            columns.append(f"{run['pipeline']} ({label})")
            values.append(run["overall"])
    return columns, values
