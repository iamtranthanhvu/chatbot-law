import pytest

from lawqa.generation.prompt_builder import build_messages
from lawqa.retrieval.context_packer import pack_context
from tests.unit.pipelines.conftest import WordCounter, make_chunk

SOURCES = pack_context([make_chunk("188", "Điều kiện chuyển nhượng")], WordCounter(), 1000)
QUESTION = "Tôi muốn bán đất chưa có sổ đỏ được không?"


def _user(messages: list[dict[str, str]]) -> str:
    return messages[-1]["content"]


def test_without_intent_the_generic_prompt_is_used() -> None:
    user = _user(build_messages(QUESTION, SOURCES))

    assert QUESTION in user
    assert "Điều kiện chuyển nhượng" in user
    assert "Kết luận" not in user


def test_situation_answers_follow_conclusion_conditions_facts_basis() -> None:
    user = _user(build_messages(QUESTION, SOURCES, intent="situation"))

    sections = ["Kết luận", "Giải thích", "Thông tin nên bổ sung", "Căn cứ pháp lý"]
    positions = [user.index(f"**{section}:**") for section in sections]
    assert positions == sorted(positions)
    assert "mức phạt" in user


def test_situation_prompt_lists_the_facts_the_question_leaves_open() -> None:
    user = _user(
        build_messages(
            QUESTION,
            SOURCES,
            intent="situation",
            missing_facts=["Đất có tranh chấp không", "Đất sử dụng từ năm nào"],
        )
    )

    assert "- Đất có tranh chấp không\n- Đất sử dụng từ năm nào" in user


def test_lookup_answers_quote_the_named_provision() -> None:
    user = _user(build_messages("Khoản 1 Điều 188 quy định gì?", SOURCES, intent="lookup"))

    assert "nguyên văn" in user


@pytest.mark.parametrize(
    ("intent", "marker"),
    [("procedure", "các bước"), ("topic_search", "mỗi ý")],
)
def test_other_intents_get_their_own_format(intent: str, marker: str) -> None:
    user = _user(build_messages("Thủ tục cấp sổ đỏ?", SOURCES, intent=intent))

    assert marker in user.lower()


def test_unknown_intents_fall_back_to_the_generic_prompt() -> None:
    assert build_messages(QUESTION, SOURCES, intent="out_of_scope") == build_messages(
        QUESTION, SOURCES
    )


def test_format_instructions_come_after_the_question() -> None:
    user = _user(build_messages(QUESTION, SOURCES, intent="situation"))

    assert user.index("CÂU HỎI:") < user.index("**Kết luận:**")
