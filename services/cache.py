from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from diskcache import Cache as _DiskCache
except Exception:  # pragma: no cover - falls back to memory cache
    _DiskCache = None  # type: ignore[assignment]


@dataclass
class CacheEntry:
    value: Any
    expires_at: float | None


class TTLCache:
    """Thread-safe TTL cache with optional disk persistence.

    Uses ``diskcache`` when available so cached values survive restarts.
    Falls back to an in-memory dict if the dependency is missing.
    """

    _shared_disk: _DiskCache | None = None
    _shared_lock = threading.Lock()

    def __init__(self, *, namespace: str = "default", persist: bool = True) -> None:
        self._lock = threading.RLock()
        self._namespace = namespace
        self._memory: dict[str, CacheEntry] = {}
        self._disk = self._open_disk() if persist else None

    @classmethod
    def _open_disk(cls) -> _DiskCache | None:
        if _DiskCache is None:
            return None
        with cls._shared_lock:
            if cls._shared_disk is None:
                cache_dir = Path(__file__).resolve().parent.parent / ".cache"
                cache_dir.mkdir(parents=True, exist_ok=True)
                cls._shared_disk = _DiskCache(str(cache_dir))
            return cls._shared_disk

    def _full_key(self, key: str) -> str:
        return f"{self._namespace}:{key}"

    def get(self, key: str, default: Any = None) -> Any:
        full_key = self._full_key(key)
        with self._lock:
            entry = self._memory.get(full_key)
            if entry is not None:
                if entry.expires_at is None or time.time() < entry.expires_at:
                    return entry.value
                self._memory.pop(full_key, None)

        if self._disk is not None:
            try:
                value = self._disk.get(full_key, default=None)
            except Exception:
                value = None
            if value is not None:
                # Repopulate memory layer for fast subsequent reads.
                with self._lock:
                    self._memory[full_key] = CacheEntry(value=value, expires_at=None)
                return value
        return default

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        full_key = self._full_key(key)
        expires_at = None if ttl_seconds is None else time.time() + ttl_seconds
        with self._lock:
            self._memory[full_key] = CacheEntry(value=value, expires_at=expires_at)
        if self._disk is not None:
            try:
                self._disk.set(full_key, value, expire=ttl_seconds)
            except Exception:
                pass

    def clear(self) -> None:
        with self._lock:
            self._memory.clear()
        if self._disk is not None:
            try:
                self._disk.clear()
            except Exception:
                pass

    def get_or_set(self, key: str, builder, ttl_seconds: int | None = None) -> Any:
        cached = self.get(key, default=None)
        if cached is not None:
            return cached
        value = builder()
        self.set(key, value, ttl_seconds)
        return value
