"""Redis-backed queue for the mining pipeline and an LLM-call rate limiter.

Redis is deliberately not used for anything that needs to survive a restart
with guarantees — that's Postgres's job. This is the ephemeral, fast path:
the queue of traces waiting to be mined, and a sliding-window rate limiter so
the mining service and regression runs don't blow through LLM-judge quota.
"""
from __future__ import annotations

import time
from typing import Iterable

import redis

TRACE_QUEUE_KEY = "mining:trace_queue"
RATE_LIMIT_PREFIX = "ratelimit:llm_calls"


class RedisQueue:
    def __init__(self, url: str = "redis://localhost:6379/0") -> None:
        self._client = redis.Redis.from_url(url, decode_responses=True)

    def enqueue_traces(self, trace_ids: Iterable[str]) -> int:
        ids = list(trace_ids)
        if not ids:
            return 0
        return self._client.rpush(TRACE_QUEUE_KEY, *ids)

    def dequeue_batch(self, batch_size: int = 100) -> list[str]:
        pipe = self._client.pipeline()
        pipe.lrange(TRACE_QUEUE_KEY, 0, batch_size - 1)
        pipe.ltrim(TRACE_QUEUE_KEY, batch_size, -1)
        batch, _ = pipe.execute()
        return batch

    def queue_depth(self) -> int:
        return self._client.llen(TRACE_QUEUE_KEY)


class SlidingWindowRateLimiter:
    """Allows at most `max_calls` within `window_seconds`, per `key`.

    Used to keep the LLM-as-judge verifier and the mining service's
    embedding calls from exceeding provider rate limits during a large
    regression fan-out.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0") -> None:
        self._client = redis.Redis.from_url(redis_url, decode_responses=True)

    def allow(self, key: str, max_calls: int, window_seconds: int) -> bool:
        now = time.time()
        zkey = f"{RATE_LIMIT_PREFIX}:{key}"
        pipe = self._client.pipeline()
        pipe.zremrangebyscore(zkey, 0, now - window_seconds)
        pipe.zcard(zkey)
        _, current_count = pipe.execute()
        if current_count >= max_calls:
            return False
        self._client.zadd(zkey, {str(now): now})
        self._client.expire(zkey, window_seconds)
        return True
