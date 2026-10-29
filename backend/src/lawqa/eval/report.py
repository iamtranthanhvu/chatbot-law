from pathlib import Path

from lawqa.eval.generation_runner import GenerationReport
from lawqa.eval.runner import RetrievalReport

METRICS = ("recall@5", "recall@10", "mrr@10", "ndcg@10")
GENERATION_METRICS = (
    "faithfulness",
    "correctness",
    "clarity_layperson",
    "citation_precision",
    "citation_recall",
    "invalid_citation_rate",
    "structure_ok",
    "refusal_accuracy",
    "false_refusal_rate",
    "error_rate",
    "judge_error_rate",
    "latency_ttft_p50",
    "latency_ttft_p95",
    "latency_total_p50",
    "latency_total_p95",
)

Report = RetrievalReport | GenerationReport


def write_report(report: Report, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = report.created_at.strftime("%Y%m%d-%H%M%S")
    stem = f"{report.kind}-{report.git_sha}-{stamp}"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    markdown = (
        render_markdown(report)
        if isinstance(report, RetrievalReport)
        else render_generation_markdown(report)
    )
    md_path.write_text(markdown, encoding="utf-8")
    return json_path, md_path


def render_markdown(report: RetrievalReport) -> str:
    lines = [
        f"# Đánh giá retrieval — {report.dataset or 'dataset'}",
        "",
        f"- Câu hỏi: {report.items} (có đáp án Điều: {report.evaluated})",
        f"- Ngày tham chiếu: {report.reference_date}",
        f"- git: `{report.git_sha}` · config: `{report.config_hash}`"
        f" · lúc {report.created_at:%Y-%m-%d %H:%M} UTC",
        "",
        "## Tổng quan",
        "",
        *_table(["chế độ"], [(m.mode, m.overall) for m in report.modes], METRICS),
    ]
    for title, attribute in (("Theo persona", "by_persona"), ("Theo intent", "by_intent")):
        lines += ["", f"## {title}", ""]
        rows = [
            (f"{mode.mode} · {group}", values)
            for mode in report.modes
            for group, values in getattr(mode, attribute).items()
        ]
        lines += _table(["chế độ · nhóm"], rows, METRICS)

    lines += ["", "## Câu hỏi chưa tìm đủ Điều trong top 10", ""]
    for mode in report.modes:
        missed = [item_id for item_id, m in mode.per_item.items() if m["recall@10"] < 1.0]
        lines.append(f"**{mode.mode}** ({len(missed)}):")
        lines += [f"- {item_id} — {report.questions[item_id]}" for item_id in missed] or ["- —"]
        lines.append("")
    return "\n".join(lines)


def render_generation_markdown(report: GenerationReport) -> str:
    lines = [
        f"# Đánh giá câu trả lời — {report.dataset or 'dataset'}",
        "",
        f"- Pipeline: `{report.pipeline}` · judge: `{report.judge_model}`"
        f" · câu hỏi: {report.items}",
        f"- Ngày tham chiếu: {report.reference_date}",
        f"- git: `{report.git_sha}` · config: `{report.config_hash}`"
        f" · lúc {report.created_at:%Y-%m-%d %H:%M} UTC",
        "",
        "## Tổng quan",
        "",
        "| metric | giá trị |",
        "|---|---|",
        *(
            f"| {metric} | {report.overall[metric]:.3f} |"
            for metric in GENERATION_METRICS
            if metric in report.overall
        ),
    ]
    for title, groups in (("Theo persona", report.by_persona), ("Theo intent", report.by_intent)):
        lines += ["", f"## {title}", ""]
        lines += _table(["nhóm"], list(groups.items()), GENERATION_METRICS[:10])

    lines += ["", "## Từng câu", ""]
    for result in report.per_item.values():
        status = result.error or ("từ chối" if result.refused else "trả lời")
        shape = {True: " · đúng khung", False: " · sai khung", None: ""}[result.structure_ok]
        scores = (
            f"F {result.scores.faithfulness:.2f} · C {result.scores.correctness:.2f}"
            f" · R {result.scores.clarity:.2f}"
            if result.scores
            else (result.judge_error or "chưa chấm")
        )
        lines += [
            f"### {result.id} ({result.persona}, {result.intent}"
            f" → {result.predicted_intent or '—'}) — {result.question}",
            f"*{status}*{shape} · {scores} · trích {', '.join(result.cited_articles) or '—'}"
            f" · trích sai {result.invalid_citations or '—'} · {result.latency_ms}",
            "",
            result.answer.strip() or "_(không có câu trả lời)_",
            "",
        ]
    return "\n".join(lines)


def _table(
    head: list[str], rows: list[tuple[str, dict[str, float]]], metrics: tuple[str, ...]
) -> list[str]:
    lines = [
        "| " + " | ".join([*head, *metrics]) + " |",
        "|" + "---|" * (len(head) + len(metrics)),
    ]
    for name, values in rows:
        cells = [f"{values[m]:.3f}" if m in values else "—" for m in metrics]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return lines
