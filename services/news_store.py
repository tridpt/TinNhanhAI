"""Persistent news article store backed by SQLite.

Articles are accumulated across refreshes so older news doesn't disappear.
Each topic keeps at most :data:`MAX_ARTICLES_PER_TOPIC` articles, pruning
the oldest when the cap is exceeded.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "news.db"
MAX_ARTICLES_PER_TOPIC = 200

_LOCK = threading.Lock()

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
        CREATE TABLE IF NOT EXISTS articles (
            url         TEXT NOT NULL,
            topic       TEXT NOT NULL,
            title       TEXT NOT NULL DEFAULT '',
            summary     TEXT NOT NULL DEFAULT '',
            source      TEXT NOT NULL DEFAULT '',
            thumbnail   TEXT NOT NULL DEFAULT '',
            published_at TEXT NOT NULL DEFAULT '',
            published_label TEXT NOT NULL DEFAULT '',
            added_at    INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (url, topic)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_articles_topic_added ON articles(topic, added_at DESC)"
    )
    _CONN = conn
    _CONN_PATH = DB_PATH
    return conn


def upsert_articles(topic: str, items: list[dict[str, Any]]) -> int:
    """Insert new articles, skip duplicates. Returns count of new inserts."""

    if not items:
        return 0

    import time

    now = int(time.time())
    inserted = 0

    with _LOCK:
        conn = _open()
        for item in items:
            url = (item.get("url") or "").strip()
            if not url:
                continue
            try:
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO articles
                        (url, topic, title, summary, source, thumbnail, published_at, published_label, added_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        url,
                        topic,
                        item.get("title") or "",
                        item.get("summary") or "",
                        item.get("source") or "",
                        item.get("thumbnail") or "",
                        item.get("published_at") or "",
                        item.get("published_label") or "",
                        now,
                    ),
                )
                # ``rowcount`` is per-statement: 1 when the row was inserted,
                # 0 when ``OR IGNORE`` skipped a duplicate. (``total_changes``
                # would over-count since the connection is now shared.)
                if cur.rowcount:
                    inserted += 1
            except Exception:
                continue

        # Prune oldest if over cap.
        count = conn.execute(
            "SELECT COUNT(*) FROM articles WHERE topic = ?", (topic,)
        ).fetchone()[0]
        if count > MAX_ARTICLES_PER_TOPIC:
            excess = count - MAX_ARTICLES_PER_TOPIC
            conn.execute(
                """
                DELETE FROM articles WHERE rowid IN (
                    SELECT rowid FROM articles
                    WHERE topic = ?
                    ORDER BY added_at ASC, published_at ASC
                    LIMIT ?
                )
                """,
                (topic, excess),
            )
    return inserted


def get_articles(topic: str, *, offset: int = 0, limit: int = 20) -> list[dict[str, Any]]:
    """Return articles for a topic, newest first, with pagination."""

    with _LOCK:
        conn = _open()
        rows = conn.execute(
            """
            SELECT url, title, summary, source, thumbnail, published_at, published_label
            FROM articles
            WHERE topic = ?
            ORDER BY published_at DESC, added_at DESC
            LIMIT ? OFFSET ?
            """,
            (topic, limit, offset),
        ).fetchall()

    return [
        {
            "url": row[0],
            "title": row[1],
            "summary": row[2],
            "source": row[3],
            "thumbnail": row[4],
            "published_at": row[5],
            "published_label": row[6],
        }
        for row in rows
    ]


def count_articles(topic: str) -> int:
    with _LOCK:
        conn = _open()
        return conn.execute(
            "SELECT COUNT(*) FROM articles WHERE topic = ?", (topic,)
        ).fetchone()[0]


def search_articles(
    query: str,
    *,
    topic: str | None = None,
    source: str | None = None,
    limit: int = 40,
) -> list[dict[str, Any]]:
    """Full-text-ish search across all stored articles.

    Matches the query (accent-insensitive on the Python side is overkill here;
    we use SQL ``LIKE`` on title/summary/source) and optionally narrows by
    topic or source. Results are de-duplicated by URL (an article can live
    under several topics) and returned newest-first.
    """

    query = (query or "").strip()
    where = []
    params: list[Any] = []

    if query:
        like = f"%{query}%"
        where.append("(title LIKE ? OR summary LIKE ? OR source LIKE ?)")
        params.extend([like, like, like])
    if topic:
        where.append("topic = ?")
        params.append(topic)
    if source:
        where.append("source = ?")
        params.append(source)

    clause = (" WHERE " + " AND ".join(where)) if where else ""
    # Over-fetch so dedup by URL still leaves a full page.
    sql = (
        "SELECT url, title, summary, source, thumbnail, published_at, published_label, topic"
        f" FROM articles{clause}"
        " ORDER BY published_at DESC, added_at DESC"
        " LIMIT ?"
    )
    params.append(max(limit * 3, limit))

    with _LOCK:
        conn = _open()
        rows = conn.execute(sql, params).fetchall()

    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for row in rows:
        url = row[0]
        if url in seen:
            continue
        seen.add(url)
        results.append(
            {
                "url": url,
                "title": row[1],
                "summary": row[2],
                "source": row[3],
                "thumbnail": row[4],
                "published_at": row[5],
                "published_label": row[6],
                "topic": row[7],
            }
        )
        if len(results) >= limit:
            break
    return results


def list_sources() -> list[str]:
    """Distinct article sources currently in the store (for filter chips)."""

    with _LOCK:
        conn = _open()
        rows = conn.execute(
            "SELECT DISTINCT source FROM articles WHERE source != '' ORDER BY source"
        ).fetchall()
    return [row[0] for row in rows]
