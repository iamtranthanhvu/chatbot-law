import json
from collections.abc import Sequence
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError

from lawqa.eval.dataset import EvalItem
from lawqa.generation.llm_client import LLMError, Message
from lawqa.pipelines.base import Source

_SYSTEM = """Bạn là giám khảo chấm câu trả lời của một hệ thống hỏi đáp pháp luật đất đai.
Chấm 3 tiêu chí, mỗi tiêu chí là số thực từ 0 đến 1:
- faithfulness: mọi nhận định trong CÂU TRẢ LỜI đều có căn cứ trong NGUỒN
  (1 = không có ý nào bịa hoặc gán sai nguồn).
- correctness: CÂU TRẢ LỜI đúng và đủ ý so với ĐÁP ÁN MẪU (1 = đúng và đủ các ý chính).
- clarity: người không học luật đọc có hiểu không (1 = rõ ràng, giải thích thuật ngữ khi cần).
Chỉ trả về JSON đúng schema, không giải thích ngoài JSON."""

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "faithfulness": {"type": "number", "minimum": 0, "maximum": 1},
        "correctness": {"type": "number", "minimum": 0, "maximum": 1},
        "clarity": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": "string"},
    },
    "required": ["faithfulness", "correctness", "clarity", "reason"],
}


class JudgeScores(BaseModel):
    faithfulness: float = Field(ge=0, le=1)
    correctness: float = Field(ge=0, le=1)
    clarity: float = Field(ge=0, le=1)
    reason: str = ""


class JudgeConfigError(ValueError):
    pass


class CompletingLLM(Protocol):
    @property
    def model(self) -> str: ...

    async def complete(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> str: ...


def check_judge_config(
    *, generator: dict[str, str], judge: dict[str, str], allow_self_judge: bool
) -> None:
    """A model grading its own answers is biased; only allow it when asked for explicitly."""
    same = generator["base_url"].rstrip("/") == judge["base_url"].rstrip("/") and (
        generator["model"] == judge["model"]
    )
    if same and not allow_self_judge:
        raise JudgeConfigError(
            f"Judge trùng model đang được đánh giá ({judge['model']}). Đặt JUDGE_MODEL khác "
            "hoặc dùng --allow-self-judge nếu thật sự muốn."
        )


class Judge:
    def __init__(self, llm: CompletingLLM, *, attempts: int = 2) -> None:
        self._llm = llm
        self._attempts = attempts

    @property
    def model(self) -> str:
        return self._llm.model

    async def score(
        self, item: EvalItem, answer: str, sources: Sequence[Source]
    ) -> tuple[JudgeScores | None, str | None]:
        messages = _messages(item, answer, sources)
        error = "không gọi được judge"
        for _ in range(self._attempts):
            try:
                raw = await self._llm.complete(
                    messages,
                    temperature=0.0,
                    max_tokens=400,
                    response_format={"type": "json_schema", "json_schema": {"schema": _SCHEMA}},
                )
                return JudgeScores.model_validate(json.loads(raw)), None
            except (json.JSONDecodeError, ValidationError) as exc:
                error = f"judge trả JSON không hợp lệ: {exc}"[:300]
            except LLMError as exc:
                error = f"lỗi gọi judge: {exc}"[:300]
        return None, error


def _messages(item: EvalItem, answer: str, sources: Sequence[Source]) -> list[Message]:
    context = "\n\n".join(source.context or source.snippet for source in sources) or "(trống)"
    user = (
        f"CÂU HỎI: {item.question}\n\nNGUỒN:\n{context}\n\n"
        f"ĐÁP ÁN MẪU: {item.reference_answer}\n\nCÂU TRẢ LỜI CẦN CHẤM:\n{answer}"
    )
    return [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}]
