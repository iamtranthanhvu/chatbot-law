import typer

app = typer.Typer(help="Law QA — công cụ vận hành (nạp văn bản, tìm kiếm, hỏi đáp, đánh giá).")


@app.callback()
def main() -> None:
    """Law QA operator CLI."""
