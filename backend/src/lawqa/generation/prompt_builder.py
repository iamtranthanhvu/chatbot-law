from collections.abc import Sequence
from functools import cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from lawqa.generation.llm_client import Message
from lawqa.retrieval.context_packer import ContextSource

_PROMPTS_DIR = Path(__file__).parent / "prompts"


@cache
def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(_PROMPTS_DIR),
        undefined=StrictUndefined,
        keep_trailing_newline=False,
        autoescape=False,
    )


INTENT_FORMATS = ("situation", "lookup", "topic_search", "procedure")


def build_messages(
    question: str,
    sources: list[ContextSource],
    *,
    intent: str | None = None,
    missing_facts: Sequence[str] = (),
) -> list[Message]:
    env = _environment()
    answer_format = ""
    if intent in INTENT_FORMATS:
        answer_format = (
            env.get_template(f"intents/{intent}.jinja")
            .render(missing_facts=list(missing_facts))
            .strip()
        )
    return [
        {"role": "system", "content": env.get_template("system.jinja").render().strip()},
        {
            "role": "user",
            "content": env.get_template("user.jinja")
            .render(question=question, sources=sources, format=answer_format)
            .strip(),
        },
    ]
