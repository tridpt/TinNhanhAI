"""SQLite-backed cache for AI article summaries.

Summarising an article costs one Gemini call, which on the free tier is a
scarce resource. Since an article's text never changes, we cache the result
keyed by a hash of (title + content) so re-opening the same article returns
instantly without burning quota.

The store mirrors the tiny stdlib-``sqlite3`` style used by
:mod:`services.history`: one table, a module-level lock, and a sampling-based
prune so the file never grows unbounded.
"""

from __future__ import annotations

import hashlib
import random
import sqlite3
import threading
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "summaries.db"

_LOCK = threading.Lock()
_RETENTION_DAYS = 30
# Sampling probability per write to trigger a background prune of old rows.
_PRUNE_PROBABILITY = 1 / 100

_CONN: sqlite3.Connection | None = None
_CONN_PATH: Path | None = None


def _open() -> sqlite3.Connection:
    """Return a process-wide connection, (re)created only when the path changes.

    One cached connection (``check_same_thread=False``) serialised by the
    module ``_LOCK`` avoids re-opening + ``CREATE TABLE`` on every query. The
    cache is keyed on ``DB_PATH`` so tests that monkeypatch it to a temp file
    still get a fresh database.
    """

    global _CONN, _CONN_PATH
    if _CONN is not None and _CONN_PATH == DB_PATH:
        return _CONN
    if _CONN is not None:
        try:
            _CONN.close()
        except Exception:
            pass
        _CONN = None

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        DB_PATH, timeout=5.0, isolation_level=None, check_same_thread=False
    )
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS summaries (
            hash    TEXT    NOT NULL PRIMARY KEY,
            title   TEXT    NOT NULL DEFAULT '',
            summary TEXT    NOT NULL,
            ts      INTEGER NOT NULL
        )
        """
    )
    _CONN = conn
    _CONN_PATH = DB_PATH
    return conn


def make_key(title: str, content: str) -> str:
    """Stable hash for an article's summarisable text."""

    raw = f"{(title or '').strip()}\n{(content or '').strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_summary(title: str, content: str) -> str | None:
    """Return a cached summary for this article, or ``None`` if not cached."""

    key = make_key(title, content)
    with _LOCK:
        conn = _open()
        row = conn.execute(
            "SELECT summary FROM summaries WHERE hash = ?", (key,)
        ).fetchone()
    if row and row[0]:
        return str(row[0])
    return None


def save_summary(title: str, content: str, summary: str) -> None:
    """Persist a summary so future requests skip the AI call."""

    if not summary or not summary.strip():
        return
    key = make_key(title, content)
    now = int(time.time())
    with _LOCK:
        conn = _open()
        conn.execute(
            "INSERT OR REPLACE INTO summaries(hash, title, summary, ts)"
            " VALUES (?, ?, ?, ?)",
            (key, (title or "")[:300], summary.strip(), now),
        )

    if random.random() < _PRUNE_PROBABILITY:
        try:
            prune(_RETENTION_DAYS)
        except Exception:  # pragma: no cover - defensive
            pass


def prune(days: int = 30) -> int:
    """Drop summaries older than ``days`` and return how many were removed."""

    cutoff = int(time.time()) - days * 86400
    with _LOCK:
        conn = _open()
        cur = conn.execute("DELETE FROM summaries WHERE ts < ?", (cutoff,))
        return cur.rowcount or 0
