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


def build_messages(question: str, sources: list[ContextSource]) -> list[Message]:
    env = _environment()
    return [
        {"role": "system", "content": env.get_template("system.jinja").render().strip()},
        {
            "role": "user",
            "content": env.get_template("user.jinja")
            .render(question=question, sources=sources)
            .strip(),
        },
    ]
