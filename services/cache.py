from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import config

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

    # Process-wide hit/miss counters (across all namespaces) for observability.
    _stats_lock = threading.Lock()
    _stats: dict[str, int] = {"hits": 0, "misses": 0}

    def __init__(self, *, namespace: str = "default", persist: bool = True) -> None:
        self._lock = threading.RLock()
        self._namespace = namespace
        self._memory: dict[str, CacheEntry] = {}
        self._disk = self._open_disk() if persist else None

    @classmethod
    def _record(cls, hit: bool) -> None:
        with cls._stats_lock:
            cls._stats["hits" if hit else "misses"] += 1

    @classmethod
    def stats(cls) -> dict[str, Any]:
        """Snapshot of cache hit/miss counts + hit-rate, for /api/health."""

        with cls._stats_lock:
            hits = cls._stats["hits"]
            misses = cls._stats["misses"]
        total = hits + misses
        return {
            "hits": hits,
            "misses": misses,
            "hit_rate": round(hits / total, 3) if total else 0.0,
        }

    @classmethod
    def _open_disk(cls) -> _DiskCache | None:
        if _DiskCache is None:
            return None
        with cls._shared_lock:
            if cls._shared_disk is None:
                cache_dir = config.CACHE_DIR
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
                    self._record(hit=True)
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
                self._record(hit=True)
                return value
        self._record(hit=False)
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

    # --- Stale-while-revalidate ----------------------------------------------

    _swr_refreshing: dict[str, bool] = {}
    _swr_lock = threading.Lock()

    def get_or_set_swr(
        self,
        key: str,
        builder: Callable[[], Any],
        *,
        fresh_seconds: int,
        max_age_seconds: int | None = None,
    ) -> Any:
        """Stale-while-revalidate read.

        Returns a cached value immediately when one exists, even if it is past
        its ``fresh_seconds`` window — in that case a single background thread
        is kicked off to rebuild it so the *next* caller gets fresh data. This
        keeps user-facing latency low (no waiting on slow upstream fetches)
        while data still converges to fresh in the background.

        - Within ``fresh_seconds``: return cached, no refresh.
        - Past ``fresh_seconds`` but value present: return stale + refresh in
          the background (deduplicated per key).
        - No value cached: build synchronously and store.

        Values are wrapped as ``{"v": value, "ts": stored_at}`` and held under a
        longer hard TTL (``max_age_seconds``, default ``4 * fresh_seconds``) so
        a stale-but-usable copy survives until the refresh lands.
        """

        hard_ttl = max_age_seconds if max_age_seconds is not None else fresh_seconds * 4
        wrapper = self.get(key, default=None)
        now = time.time()

        if isinstance(wrapper, dict) and "v" in wrapper and "ts" in wrapper:
            age = now - float(wrapper["ts"])
            if age < fresh_seconds:
                return wrapper["v"]
            # Stale but usable — refresh in the background, return stale now.
            self._spawn_swr_refresh(key, builder, hard_ttl)
            return wrapper["v"]

        # Cold: nothing cached yet, build synchronously.
        value = builder()
        self.set(key, {"v": value, "ts": now}, hard_ttl)
        return value

    def _spawn_swr_refresh(
        self, key: str, builder: Callable[[], Any], hard_ttl: int
    ) -> None:
        full_key = self._full_key(key)
        with self._swr_lock:
            if self._swr_refreshing.get(full_key):
                return  # a refresh is already in flight for this key
            self._swr_refreshing[full_key] = True

        def _work() -> None:
            try:
                value = builder()
                self.set(key, {"v": value, "ts": time.time()}, hard_ttl)
            except Exception:
                pass  # keep serving the stale value; try again next time
            finally:
                with self._swr_lock:
                    self._swr_refreshing.pop(full_key, None)

        threading.Thread(
            target=_work, name=f"swr-refresh-{self._namespace}", daemon=True
        ).start()
