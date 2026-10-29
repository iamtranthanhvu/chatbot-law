from pathlib import Path

from lawqa.eval.runner import RetrievalReport

METRICS = ("recall@5", "recall@10", "mrr@10", "ndcg@10")


def write_report(report: RetrievalReport, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = report.created_at.strftime("%Y%m%d-%H%M%S")
    stem = f"{report.kind}-{report.git_sha}-{stamp}"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
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
        *_table(["chế độ"], [(m.mode, m.overall) for m in report.modes]),
    ]
    for title, attribute in (("Theo persona", "by_persona"), ("Theo intent", "by_intent")):
        lines += ["", f"## {title}", ""]
        rows = [
            (f"{mode.mode} · {group}", values)
            for mode in report.modes
            for group, values in getattr(mode, attribute).items()
        ]
        lines += _table(["chế độ · nhóm"], rows)

    lines += ["", "## Câu hỏi chưa tìm đủ Điều trong top 10", ""]
    for mode in report.modes:
        missed = [item_id for item_id, m in mode.per_item.items() if m["recall@10"] < 1.0]
        lines.append(f"**{mode.mode}** ({len(missed)}):")
        lines += [f"- {item_id} — {report.questions[item_id]}" for item_id in missed] or ["- —"]
        lines.append("")
    return "\n".join(lines)


def _table(head: list[str], rows: list[tuple[str, dict[str, float]]]) -> list[str]:
    lines = [
        "| " + " | ".join([*head, *METRICS]) + " |",
        "|" + "---|" * (len(head) + len(METRICS)),
    ]
    for name, values in rows:
        cells = [f"{values.get(metric, 0.0):.3f}" for metric in METRICS]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return lines
