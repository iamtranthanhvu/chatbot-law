import json
from typing import Any

import pytest

from lawqa.generation.llm_client import LLMTimeoutError, Message
from lawqa.understanding.classifier import QueryUnderstanding, Understanding


class FakeLLM:
    model = "fake"

    def __init__(self, reply: str | Exception) -> None:
        self.reply = reply
        self.calls: list[tuple[list[Message], dict[str, Any] | None]] = []

    async def complete(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        self.calls.append((messages, response_format))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def _reply(**fields: Any) -> str:
    base = {"intent": "situation", "legal_query": "q", "missing_facts": []}
    return json.dumps({**base, **fields}, ensure_ascii=False)


async def test_parses_the_structured_reply() -> None:
    llm = FakeLLM(
        _reply(
            intent="situation",
            legal_query="Xây dựng nhà ở trên đất trồng lúa có phải chuyển mục đích sử dụng đất?",
            missing_facts=["Đất đã được chuyển mục đích chưa"],
        )
    )

    result = await QueryUnderstanding(llm).understand("Xây nhà trên đất ruộng có bị phạt không?")

    assert result == Understanding(
        intent="situation",
        legal_query="Xây dựng nhà ở trên đất trồng lúa có phải chuyển mục đích sử dụng đất?",
        missing_facts=["Đất đã được chuyển mục đích chưa"],
        fallback=False,
    )
    messages, response_format = llm.calls[0]
    assert response_format is not None and response_format["type"] == "json_schema"
    assert "Xây nhà trên đất ruộng" in messages[-1]["content"]


@pytest.mark.parametrize("reply", ["không phải JSON", _reply(intent="hỏi linh tinh")])
async def test_invalid_reply_falls_back_to_a_safe_default(reply: str) -> None:
    result = await QueryUnderstanding(FakeLLM(reply)).understand("Đất thổ cư dùng bao lâu?")

    assert result == Understanding(
        intent="topic_search", legal_query="Đất thổ cư dùng bao lâu?", fallback=True
    )


async def test_llm_failure_falls_back_and_named_articles_mean_lookup() -> None:
    llm = FakeLLM(LLMTimeoutError("quá lâu"))

    result = await QueryUnderstanding(llm).understand("Điều 100 quy định gì?")

    assert result.intent == "lookup" and result.fallback


async def test_missing_facts_are_only_kept_for_situations() -> None:
    llm = FakeLLM(_reply(intent="lookup", missing_facts=["không liên quan"]))

    result = await QueryUnderstanding(llm).understand("Điều 12 quy định gì?")

    assert result.missing_facts == []


async def test_empty_legal_query_is_replaced_by_the_question() -> None:
    result = await QueryUnderstanding(FakeLLM(_reply(legal_query="  "))).understand("Câu hỏi?")

    assert result.legal_query == "Câu hỏi?"


class RecordingRetriever:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str | None]] = []

    async def search(
        self, texts: list[str], reference_date: Any, *, mode: str | None = None
    ) -> list[Any]:
        self.calls.append((texts, mode))
        return []


async def test_qu_mode_adds_the_legal_rewrite_before_searching() -> None:
    from datetime import date

    from lawqa.understanding.classifier import UnderstandingRetriever

    inner = RecordingRetriever()
    understanding = QueryUnderstanding(FakeLLM(_reply(intent="topic_search", legal_query="đất ở")))
    retriever = UnderstandingRetriever(inner, understanding)

    await retriever.search(["thổ cư?"], date(2026, 1, 1), mode="hybrid+rerank+qu")
    await retriever.search(["thổ cư?"], date(2026, 1, 1), mode="hybrid")

    assert inner.calls == [(["thổ cư?", "đất ở"], "hybrid+rerank"), (["thổ cư?"], "hybrid")]


async def test_intent_accuracy_report() -> None:
    from lawqa.eval.dataset import EvalItem
    from lawqa.eval.understanding_eval import intent_accuracy

    items = [
        EvalItem.model_validate(
            {
                "id": str(n),
                "persona": "layperson",
                "intent": intent,
                "question": f"q{n}",
                "reference_answer": "a",
                "reference_citations": [],
            }
        )
        for n, intent in enumerate(["situation", "situation", "lookup", "out_of_scope"])
    ]
    predicted = {"0": "situation", "1": "procedure", "2": "lookup", "3": "out_of_scope"}

    report = intent_accuracy(items, predicted)

    assert report.accuracy == 0.75
    assert report.confusion["situation"] == {"situation": 1, "procedure": 1}
    assert report.mistakes == [("1", "q1", "situation", "procedure")]


async def test_lookup_requires_an_article_number_in_the_question() -> None:
    llm = FakeLLM(_reply(intent="lookup", legal_query="Điều kiện chuyển nhượng"))

    result = await QueryUnderstanding(llm).understand("Điều kiện chuyển nhượng là gì?")

    assert result.intent == "topic_search"


async def test_a_named_article_means_lookup_unless_it_is_a_situation() -> None:
    topic = await QueryUnderstanding(FakeLLM(_reply(intent="topic_search"))).understand(
        "Điều 100 quy định gì?"
    )
    situation = await QueryUnderstanding(FakeLLM(_reply(intent="situation"))).understand(
        "Tôi có giấy tờ theo Điều 100 thì được cấp sổ không?"
    )

    assert topic.intent == "lookup"
    assert situation.intent == "situation"


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Nhà nước thu hồi đất của tôi thì tôi có được bồi thường không?", "situation"),
        ("Nhà tôi bị thu hồi đất ở thì có được tái định cư không?", "situation"),
        ("Em bỏ hoang ruộng thì có bị thu hồi không?", "situation"),
        ("Thời hạn sử dụng đất nông nghiệp là bao lâu?", "topic_search"),
        ("Tôinghĩ không liên quan", "topic_search"),
    ],
)
async def test_first_person_topic_questions_are_situations(question: str, expected: str) -> None:
    result = await QueryUnderstanding(FakeLLM(_reply(intent="topic_search"))).understand(question)

    assert result.intent == expected


async def test_first_person_procedure_questions_stay_procedures() -> None:
    llm = FakeLLM(_reply(intent="procedure"))

    result = await QueryUnderstanding(llm).understand("Thủ tục để tôi làm sổ đỏ là gì?")

    assert result.intent == "procedure"
