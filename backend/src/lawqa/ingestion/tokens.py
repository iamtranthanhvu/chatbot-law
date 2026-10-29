from tokenizers import Tokenizer


class HFTokenCounter:
    """Counts tokens with the embedding model's own tokenizer (special tokens included)."""

    def __init__(self, tokenizer_name: str) -> None:
        self._tokenizer = Tokenizer.from_pretrained(tokenizer_name)

    def count(self, text: str) -> int:
        return len(self._tokenizer.encode(text).ids)
