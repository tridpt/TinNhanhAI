"""Tiny per-IP token-bucket rate limiter for Flask routes.

The implementation deliberately stays in-process: a single TinNhanh node
serves dozens of users and we do not want a Redis dependency. If you scale
horizontally, swap this for ``flask-limiter`` with a shared backend.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable

from flask import jsonify, request


class RateLimiter:
    def __init__(self, max_per_minute: int) -> None:
        self.max_per_minute = max(1, int(max_per_minute))
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = {}

    def _client_key(self) -> str:
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip() or request.remote_addr or "anon"
        return request.remote_addr or "anon"

    def check(self) -> tuple[bool, int]:
        """Returns (allowed, retry_after_seconds)."""

        now = time.time()
        cutoff = now - 60
        key = self._client_key()
        with self._lock:
            self._evict_stale(cutoff, keep=key)
            bucket = self._hits.setdefault(key, deque())
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_per_minute:
                retry_after = max(1, int(60 - (now - bucket[0])))
                return False, retry_after
            bucket.append(now)
            return True, 0

    def _evict_stale(self, cutoff: float, *, keep: str) -> None:
        """Drop buckets whose most recent hit is older than the window.

        Without this, every distinct client IP would leave a ``deque`` behind
        forever, slowly leaking memory on a long-running node. Called under the
        lock from :meth:`check`. ``keep`` is the current client, skipped so it
        is pruned by the normal popleft path below instead.
        """

        stale = [
            client
            for client, bucket in self._hits.items()
            if client != keep and (not bucket or bucket[-1] < cutoff)
        ]
        for client in stale:
            del self._hits[client]


def limit(limiter: RateLimiter) -> Callable:
    """Decorator that returns a 429 JSON response when the limit is hit."""

    def decorator(view: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            allowed, retry_after = limiter.check()
            if not allowed:
                response = jsonify(
                    {
                        "error": "rate_limited",
                        "message": "Bạn đang gửi câu hỏi quá nhanh, hãy thử lại sau.",
                        "retry_after": retry_after,
                    }
                )
                response.status_code = 429
                response.headers["Retry-After"] = str(retry_after)
                return response
            return view(*args, **kwargs)

        wrapper.__name__ = view.__name__
        return wrapper

    return decorator
