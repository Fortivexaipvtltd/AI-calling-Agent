from __future__ import annotations

import threading
import time
from collections import deque

from ..config import settings


class RateLimiter:
    """Fixed-capacity sliding-window limiter keyed by principal or client IP.

    In-process and thread-safe — correct for a single instance. For multi-instance
    deployments back this with Redis (INCR + EXPIRE); the interface stays the same.
    """

    def __init__(self, per_min: int | None = None) -> None:
        # None => read the limit from settings at call time (picks up runtime config).
        self.per_min = per_min
        self.window = 60.0
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def _limit(self) -> int:
        return self.per_min if self.per_min is not None else settings.rate_limit_per_min

    def allow(self, key: str) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds)."""
        limit = self._limit()
        now = time.monotonic()
        with self._lock:
            dq = self._hits.setdefault(key, deque())
            cutoff = now - self.window
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= limit:
                retry = int(self.window - (now - dq[0])) + 1
                return False, max(1, retry)
            dq.append(now)
            return True, 0


limiter = RateLimiter()


class RedisRateLimiter:
    """Distributed limiter for multi-instance deployments. Uses an atomic
    INCR + EXPIRE per fixed 60s window keyed by principal/IP. Falls back to the
    in-process limiter if Redis is unreachable, so a Redis outage degrades to
    per-instance limiting rather than failing open or closed unexpectedly."""

    def __init__(self, url: str, per_min: int | None = None) -> None:
        self.per_min = per_min or settings.rate_limit_per_min
        self._fallback = RateLimiter(self.per_min)
        self._client = None
        try:
            import redis  # optional dependency

            self._client = redis.Redis.from_url(url, socket_timeout=0.5,
                                                socket_connect_timeout=0.5)
            self._client.ping()
        except Exception:
            self._client = None  # degrade to in-process

    def allow(self, key: str) -> tuple[bool, int]:
        if not self._client:
            return self._fallback.allow(key)
        try:
            import time
            window = int(time.time() // 60)
            rkey = f"rl:{key}:{window}"
            pipe = self._client.pipeline()
            pipe.incr(rkey)
            pipe.expire(rkey, 60)
            count = pipe.execute()[0]
            if count > self.per_min:
                return False, 60 - int(time.time() % 60)
            return True, 0
        except Exception:
            return self._fallback.allow(key)


def build_limiter():
    """Pick the distributed limiter when a real Redis URL is configured."""
    url = settings.redis_url
    if url and not url.startswith("memory:"):
        return RedisRateLimiter(url)
    return limiter
