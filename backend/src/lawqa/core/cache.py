import hashlib
import json
import re
import unicodedata

from pydantic import BaseModel
from redis.asyncio import Redis

from lawqa.pipelines.base import DoneEvent, Source

_SPACES = re.compile(r"\s+")


def normalize_question(question: str) -> str:
    text = _SPACES.sub(" ", unicodedata.normalize("NFC", question).casefold()).strip()
    return text.rstrip("?!.… ").strip()


class CachedAnswer(BaseModel):
    intent: str | None
    sources: list[Source]
    done: DoneEvent


class AnswerCache:
    def __init__(self, redis: Redis, ttl_seconds: int, prefix: str = "answer") -> None:
        self._redis = redis
        self._ttl = ttl_seconds
        self._prefix = prefix

    def key(self, question: str, pipeline: str, config_hash: str, corpus_version: int) -> str:
        """The corpus version is part of the key, so re-ingesting retires every old answer."""
        payload = json.dumps(
            [normalize_question(question), pipeline, config_hash, corpus_version],
            ensure_ascii=False,
        )
        return f"{self._prefix}:{hashlib.sha256(payload.encode()).hexdigest()}"

    async def get(self, key: str) -> CachedAnswer | None:
        raw = await self._redis.get(key)
        return CachedAnswer.model_validate_json(raw) if raw else None

    async def set(self, key: str, answer: CachedAnswer) -> None:
        await self._redis.set(key, answer.model_dump_json(), ex=self._ttl)
