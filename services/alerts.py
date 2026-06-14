"""Price-alert store + current-price collector backed by SQLite.

Users define thresholds (e.g. "BTC ≥ 100000", "vàng SJC ≤ 90tr"); a background
watcher (:mod:`services.price_alert`) compares them against live prices and
pushes a Telegram message when crossed. Alerts are one-shot: once triggered
they are deactivated so the user isn't spammed every cycle.

The store mirrors the tiny stdlib-``sqlite3`` style used elsewhere in the
project: one table, a module-level lock.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "alerts.db"

_LOCK = threading.Lock()
VALID_DIRECTIONS = {"above", "below"}

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
        CREATE TABLE IF NOT EXISTS alerts (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            item_key      TEXT    NOT NULL,
            label         TEXT    NOT NULL DEFAULT '',
            unit          TEXT    NOT NULL DEFAULT '',
            direction     TEXT    NOT NULL,
            threshold     REAL    NOT NULL,
            active        INTEGER NOT NULL DEFAULT 1,
            created_at    INTEGER NOT NULL,
            triggered_at  INTEGER,
            triggered_price REAL
        )
        """
    )
    _CONN = conn
    _CONN_PATH = DB_PATH
    return conn


def add_alert(
    item_key: str,
    direction: str,
    threshold: float,
    *,
    label: str = "",
    unit: str = "",
) -> dict[str, Any] | None:
    """Create an alert. Returns the row dict, or ``None`` on invalid input."""

    item_key = (item_key or "").strip()
    direction = (direction or "").strip().lower()
    if not item_key or direction not in VALID_DIRECTIONS:
        return None
    try:
        threshold = float(threshold)
    except (TypeError, ValueError):
        return None

    now = int(time.time())
    with _LOCK:
        conn = _open()
        cur = conn.execute(
            "INSERT INTO alerts(item_key, label, unit, direction, threshold, active, created_at)"
            " VALUES (?, ?, ?, ?, ?, 1, ?)",
            (item_key, label or "", unit or "", direction, threshold, now),
        )
        alert_id = cur.lastrowid
    return {
        "id": alert_id,
        "item_key": item_key,
        "label": label,
        "unit": unit,
        "direction": direction,
        "threshold": threshold,
        "active": 1,
        "created_at": now,
    }


def list_alerts(*, active_only: bool = False) -> list[dict[str, Any]]:
    clause = " WHERE active = 1" if active_only else ""
    with _LOCK:
        conn = _open()
        rows = conn.execute(
            "SELECT id, item_key, label, unit, direction, threshold, active,"
            " created_at, triggered_at, triggered_price"
            f" FROM alerts{clause} ORDER BY active DESC, created_at DESC"
        ).fetchall()
    return [
        {
            "id": r[0],
            "item_key": r[1],
            "label": r[2],
            "unit": r[3],
            "direction": r[4],
            "threshold": r[5],
            "active": r[6],
            "created_at": r[7],
            "triggered_at": r[8],
            "triggered_price": r[9],
        }
        for r in rows
    ]


def delete_alert(alert_id: int) -> bool:
    with _LOCK:
        conn = _open()
        cur = conn.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
        return (cur.rowcount or 0) > 0


def mark_triggered(alert_id: int, price: float) -> None:
    now = int(time.time())
    with _LOCK:
        conn = _open()
        conn.execute(
            "UPDATE alerts SET active = 0, triggered_at = ?, triggered_price = ?"
            " WHERE id = ?",
            (now, float(price), alert_id),
        )


def is_crossed(direction: str, price: float, threshold: float) -> bool:
    """Return True when ``price`` has reached/crossed ``threshold``."""

    if direction == "above":
        return price >= threshold
    if direction == "below":
        return price <= threshold
    return False
