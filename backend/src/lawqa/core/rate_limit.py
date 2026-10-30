import math
import time
import uuid
from typing import NamedTuple

from redis.asyncio import Redis


class RateLimit(NamedTuple):
    requests: int
    window_seconds: int


class RateDecision(NamedTuple):
    allowed: bool
    retry_after: int = 0


class RateLimiter:
    """Sliding windows: a sorted set per client and limit holds the request times of the last
    window, so "10 per minute" holds over any 60 seconds, not only per clock minute.
    Refused requests are removed again and do not prolong the wait."""

    def __init__(self, redis: Redis, limits: tuple[RateLimit, ...], prefix: str = "rl") -> None:
        self._redis = redis
        self._limits = limits
        self._prefix = prefix

    async def hit(self, client: str) -> RateDecision:
        now = time.time()
        member = f"{now:.6f}-{uuid.uuid4().hex[:8]}"
        keys = [f"{self._prefix}:{limit.window_seconds}:{client}" for limit in self._limits]
        async with self._redis.pipeline(transaction=True) as pipe:
            for key, limit in zip(keys, self._limits, strict=True):
                pipe.zremrangebyscore(key, "-inf", now - limit.window_seconds)
                pipe.zadd(key, {member: now})
                pipe.zcard(key)
                pipe.zrange(key, 0, 0, withscores=True)
                pipe.expire(key, limit.window_seconds)
            results = await pipe.execute()

        retry_after = 0
        for i, limit in enumerate(self._limits):
            count, oldest = results[i * 5 + 2], results[i * 5 + 3]
            if count > limit.requests:
                wait = oldest[0][1] + limit.window_seconds - now
                retry_after = max(retry_after, max(1, math.ceil(wait)))
        if retry_after:
            async with self._redis.pipeline(transaction=True) as pipe:
                for key in keys:
                    pipe.zrem(key, member)
                await pipe.execute()
        return RateDecision(allowed=retry_after == 0, retry_after=retry_after)
