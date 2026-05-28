"""Price history storage backed by SQLite.

Each price fetch appends one row per metric so the dashboard can render a
7-day sparkline. The store is intentionally tiny (stdlib ``sqlite3``) and
keeps everything in ``data/history.db`` which is gitignored.

Writes are throttled by :data:`_MIN_INTERVAL_SECONDS`: a metric can record
at most one point per ~4 minutes, which prevents duplicates when the user
mashes the refresh button or when waitress workers race on startup.

Old rows are automatically pruned: every successful insert has a small
probability (:data:`_PRUNE_PROBABILITY`) of triggering a background
``DELETE FROM price_history WHERE ts < cutoff`` so the database never
needs an external cron job.
"""

from __future__ import annotations

import random
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "history.db"

_LOCK = threading.Lock()
_MIN_INTERVAL_SECONDS = 240
_RETENTION_DAYS = 60
# Probability per successful insert that we kick off a background prune.
# 1/200 ≈ once every ~14 hours given the throttled write rate, which is
# plenty to keep the SQLite file from growing unbounded over months.
_PRUNE_PROBABILITY = 1 / 200


def _open() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5.0, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS price_history (
            key   TEXT    NOT NULL,
            ts    INTEGER NOT NULL,
            value REAL    NOT NULL,
            label TEXT    NOT NULL DEFAULT '',
            PRIMARY KEY (key, ts)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_price_history_key_ts ON price_history(key, ts)"
    )
    return conn


def record_price(key: str, value: float | None, *, label: str = "") -> bool:
    """Append a (key, ts, value) row when at least 4 minutes passed.

    Returns ``True`` if a row was inserted, ``False`` if the input was
    rejected or throttled.
    """

    if not key or value is None:
        return False
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    if numeric != numeric or numeric <= 0:  # NaN or non-positive guard
        return False

    now = int(time.time())
    cutoff = now - _MIN_INTERVAL_SECONDS
    inserted = False

    with _LOCK:
        conn = _open()
        try:
            row = conn.execute(
                "SELECT MAX(ts) FROM price_history WHERE key = ?", (key,)
            ).fetchone()
            last_ts = int(row[0]) if row and row[0] is not None else 0
            if last_ts >= cutoff:
                return False
            conn.execute(
                "INSERT OR IGNORE INTO price_history(key, ts, value, label)"
                " VALUES (?, ?, ?, ?)",
                (key, now, numeric, label or ""),
            )
            inserted = True
        finally:
            conn.close()

    if inserted and random.random() < _PRUNE_PROBABILITY:
        # Best-effort: never raise from a sampling-based maintenance hook.
        try:
            prune(_RETENTION_DAYS)
        except Exception:  # pragma: no cover - defensive
            pass
    return inserted


def get_history(key: str, *, days: int = 7, limit: int = 200) -> list[dict[str, Any]]:
    """Return ascending datapoints for ``key`` within the last ``days``."""

    if not key:
        return []
    cutoff = int(time.time()) - days * 86400

    with _LOCK:
        conn = _open()
        try:
            rows = conn.execute(
                "SELECT ts, value FROM price_history"
                " WHERE key = ? AND ts >= ?"
                " ORDER BY ts ASC",
                (key, cutoff),
            ).fetchall()
        finally:
            conn.close()

    if not rows:
        return []

    # Downsample to at most `limit` points so payloads stay small.
    if len(rows) > limit:
        step = len(rows) / limit
        sampled = [rows[min(int(i * step), len(rows) - 1)] for i in range(limit)]
        rows = sampled

    return [{"ts": int(ts), "value": float(value)} for ts, value in rows]


def prune(days: int = 60) -> int:
    """Drop rows older than ``days`` and return how many were removed."""

    cutoff = int(time.time()) - days * 86400
    with _LOCK:
        conn = _open()
        try:
            cur = conn.execute("DELETE FROM price_history WHERE ts < ?", (cutoff,))
            return cur.rowcount or 0
        finally:
            conn.close()
