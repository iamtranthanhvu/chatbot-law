import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

Persona = Literal["layperson", "professional"]
Intent = Literal["situation", "lookup", "topic_search", "procedure", "out_of_scope"]


class Citation(BaseModel):
    so_hieu: str = "45/2013/QH13"
    dieu: str
    khoan: int | None = None
    diem: str | None = None


class EvalItem(BaseModel):
    id: str
    question: str
    reference_answer: str
    reference_citations: list[Citation]
    intent: Intent
    persona: Persona
    tags: list[str] = Field(default_factory=list)

    @property
    def has_references(self) -> bool:
        return bool(self.reference_citations)


def load_dataset(path: Path) -> list[EvalItem]:
    items = [
        EvalItem.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    seen: set[str] = set()
    for item in items:
        if item.id in seen:
            raise ValueError(f"id bị trùng trong {path.name}: {item.id}")
        seen.add(item.id)
    return items


def dump_item(item: EvalItem) -> str:
    return json.dumps(item.model_dump(exclude_defaults=True), ensure_ascii=False)
