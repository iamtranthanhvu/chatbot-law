import unicodedata

import pytest

from lawqa.retrieval.bm25 import BM25Params, average_length, encode_document, encode_query, token_id
from lawqa.retrieval.bm25_tokenizer import tokenize


def test_same_tokens_regardless_of_case_spacing_and_unicode_form() -> None:
    decomposed = unicodedata.normalize("NFD", "người  lao   động")

    assert tokenize("Người lao động") == tokenize(decomposed)


def test_unigrams_and_bigrams_of_syllables() -> None:
    assert tokenize("người lao động") == [
        "người",
        "lao",
        "động",
        "người lao",
        "lao động",
    ]


def test_bigrams_do_not_cross_punctuation() -> None:
    tokens = tokenize("đất ở, đất nông nghiệp")

    assert "đất ở" in tokens
    assert "ở đất" not in tokens
    assert "đất nông" in tokens


def test_document_number_is_a_single_token() -> None:
    tokens = tokenize("Luật số 45/2013/QH13 và Nghị định 43/2014/NĐ-CP")

    assert "45/2013/qh13" in tokens
    assert "43/2014/nđ-cp" in tokens
    assert not {"45", "2013", "qh13", "43", "2014"} & set(tokens)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Điều 100", {"điều 100"}),
        ("khoản 2 Điều 5", {"khoản 2", "điều 5"}),
        ("điểm đ khoản 1 Điều 100", {"điểm đ", "khoản 1", "điều 100"}),
        ("Chương VII", {"chương vii"}),
        ("Mục 2", {"mục 2"}),
    ],
)
def test_structural_references_are_single_tokens(text: str, expected: set[str]) -> None:
    assert expected <= set(tokenize(text))


def test_ordinary_words_starting_like_references_are_not_references() -> None:
    tokens = tokenize("điều kiện sử dụng đất vào mục đích khác theo khoản này")

    # Identifiers are emitted first; none were found, so the first token is a plain syllable.
    assert tokens[0] == "điều"
    assert "điều kiện" in tokens
    assert "mục đích" in tokens


def test_token_id_is_stable_uint32() -> None:
    first = token_id("đất ở")

    assert first == token_id("đất ở")
    assert 0 <= first < 2**32


PARAMS = BM25Params(avgdl=10.0)


def test_document_vector_is_deterministic_with_sorted_unique_indices() -> None:
    vector = encode_document("đất ở tại nông thôn, đất ở tại đô thị", PARAMS)

    assert vector == encode_document("đất ở tại nông thôn, đất ở tại đô thị", PARAMS)
    assert vector.indices == sorted(set(vector.indices))
    assert len(vector.indices) == len(vector.values)
    assert all(value > 0 for value in vector.values)


def _weight(text: str, token: str, params: BM25Params = PARAMS) -> float:
    vector = encode_document(text, params)
    return dict(zip(vector.indices, vector.values, strict=True))[token_id(token)]


def test_term_frequency_saturates() -> None:
    once = _weight("đất", "đất")
    three_times = _weight("đất đất đất", "đất")

    assert once < three_times < PARAMS.k1 + 1


def test_longer_documents_get_lower_weight_for_the_same_frequency() -> None:
    short = _weight("thu hồi đất", "thu hồi")
    long = _weight("thu hồi đất " + "quy định chi tiết " * 10, "thu hồi")

    assert long < short


def test_query_vector_has_unit_weight_per_unique_token() -> None:
    tokens = tokenize("đất ở đất ở")
    vector = encode_query("đất ở đất ở")

    assert vector.values == [1.0] * len(vector.indices)
    assert len(vector.indices) == len(set(tokens)) < len(tokens)


def test_average_length_counts_tokens() -> None:
    assert average_length(["đất", "người lao động"]) == pytest.approx((1 + 5) / 2)
