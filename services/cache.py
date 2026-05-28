from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class CacheEntry:
    value: Any
    expires_at: float | None


class TTLCache:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._data: dict[str, CacheEntry] = {}

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            entry = self._data.get(key)
            if not entry:
                return default
            if entry.expires_at is not None and time.time() >= entry.expires_at:
                self._data.pop(key, None)
                return default
            return entry.value

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        expires_at = None if ttl_seconds is None else time.time() + ttl_seconds
        with self._lock:
            self._data[key] = CacheEntry(value=value, expires_at=expires_at)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def get_or_set(self, key: str, builder, ttl_seconds: int | None = None) -> Any:
        cached = self.get(key, default=None)
        if cached is not None:
            return cached
        value = builder()
        self.set(key, value, ttl_seconds)
        return value

