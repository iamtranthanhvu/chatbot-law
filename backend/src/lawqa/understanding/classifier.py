import json
import logging
import re
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, ValidationError

from lawqa.generation.llm_client import LLMError, Message
from lawqa.understanding.citation_regex import extract_citations

logger = logging.getLogger("lawqa.understanding")

Intent = Literal["situation", "lookup", "topic_search", "procedure", "out_of_scope"]

# A question about the asker's own land is a situation even when it reads like a topic question.
_FIRST_PERSON = re.compile(
    r"(?<![^\W_])(tôi|mình|em|chúng tôi|gia đình tôi)(?![^\W_])", re.IGNORECASE
)

_SYSTEM = (Path(__file__).parent / "prompts" / "understand.txt").read_text(encoding="utf-8")

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": ["situation", "lookup", "topic_search", "procedure", "out_of_scope"],
        },
        "legal_query": {"type": "string"},
        "missing_facts": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
    },
    "required": ["intent", "legal_query", "missing_facts"],
}


class Understanding(BaseModel):
    intent: Intent
    legal_query: str
    missing_facts: list[str] = Field(default_factory=list)
    fallback: bool = False


class CompletingLLM(Protocol):
    async def complete(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> str: ...


class QueryUnderstanding:
    """One structured LLM call before retrieval; any failure falls back to a safe default."""

    def __init__(self, llm: CompletingLLM) -> None:
        self._llm = llm

    async def understand(self, question: str) -> Understanding:
        try:
            raw = await self._llm.complete(
                [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": question}],
                temperature=0.0,
                max_tokens=300,
                response_format={"type": "json_schema", "json_schema": {"schema": _SCHEMA}},
            )
            parsed = Understanding.model_validate({**json.loads(raw), "fallback": False})
        except (json.JSONDecodeError, ValidationError, LLMError, TypeError) as error:
            logger.warning("understanding.fallback", extra={"error": str(error)[:200]})
            return _fallback(question)

        legal_query = parsed.legal_query.strip() or question
        intent = _settle_situation(_settle_lookup(parsed.intent, question), question)
        facts = parsed.missing_facts if intent == "situation" else []
        return parsed.model_copy(
            update={"intent": intent, "legal_query": legal_query, "missing_facts": facts}
        )


def _settle_lookup(intent: Intent, question: str) -> Intent:
    """ "lookup" is decided by whether an article number is written, not by the model."""
    named = bool(extract_citations(question))
    if intent == "lookup" and not named:
        return "topic_search"
    if named and intent in ("topic_search", "procedure"):
        return "lookup"
    return intent


def _settle_situation(intent: Intent, question: str) -> Intent:
    if intent == "topic_search" and _FIRST_PERSON.search(question):
        return "situation"
    return intent


def _fallback(question: str) -> Understanding:
    intent: Intent = "lookup" if extract_citations(question) else "topic_search"
    return Understanding(intent=intent, legal_query=question, fallback=True)


class ModeRetriever(Protocol):
    async def search(
        self, texts: list[str], reference_date: Any, *, mode: str | None = None
    ) -> list[Any]: ...


UNDERSTANDING_SUFFIX = "+qu"


class UnderstandingRetriever:
    """For retrieval ablation: a "+qu" mode searches with the question's legal rewrite too."""

    def __init__(self, inner: ModeRetriever, understanding: QueryUnderstanding) -> None:
        self._inner = inner
        self._understanding = understanding

    async def search(
        self, texts: list[str], reference_date: Any, *, mode: str | None = None
    ) -> list[Any]:
        if mode is None or not mode.endswith(UNDERSTANDING_SUFFIX):
            return await self._inner.search(texts, reference_date, mode=mode)
        understood = await self._understanding.understand(texts[0])
        queries = list(texts)
        if understood.legal_query not in queries:
            queries.append(understood.legal_query)
        return await self._inner.search(
            queries, reference_date, mode=mode.removesuffix(UNDERSTANDING_SUFFIX)
        )
