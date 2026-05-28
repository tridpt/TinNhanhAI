"""Tests for the SQLite price history layer."""

from __future__ import annotations

import time


def test_record_price_inserts_and_returns_history(isolated_history, monkeypatch):
    h = isolated_history
    # Force two distinct timestamps so the (key, ts) primary key accepts both.
    fake_now = [1_700_000_000]

    def fake_time():
        fake_now[0] += 1
        return fake_now[0]

    monkeypatch.setattr(h.time, "time", fake_time)

    assert h.record_price("gold", 4500.0, label="Vàng") is True
    assert h.record_price("gold", 4510.0, label="Vàng") is True

    points = h.get_history("gold", days=7)

    assert len(points) == 2
    assert {p["value"] for p in points} == {4500.0, 4510.0}
    # Points should arrive sorted ascending by timestamp.
    assert points[0]["ts"] <= points[1]["ts"]


def test_record_price_rejects_invalid_inputs(isolated_history):
    h = isolated_history

    assert h.record_price("", 100.0) is False
    assert h.record_price("gold", None) is False
    assert h.record_price("gold", float("nan")) is False
    assert h.record_price("gold", -10) is False
    assert h.record_price("gold", "not a number") is False
    assert h.get_history("gold") == []


def test_record_price_throttles_rapid_writes(isolated_history, monkeypatch):
    h = isolated_history
    monkeypatch.setattr(h, "_MIN_INTERVAL_SECONDS", 600)

    assert h.record_price("oil", 90.0) is True
    assert h.record_price("oil", 91.0) is False  # throttled

    points = h.get_history("oil", days=7)
    assert len(points) == 1
    assert points[0]["value"] == 90.0


def test_get_history_filters_by_days_window(isolated_history):
    """Old datapoints fall out of a narrow window."""

    h = isolated_history
    # Insert manually to bypass the throttle and forge timestamps.
    import sqlite3

    now = int(time.time())
    conn = sqlite3.connect(h.DB_PATH)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS price_history(key TEXT, ts INTEGER, value REAL, label TEXT, PRIMARY KEY(key, ts))"
        )
        for offset_days, value in [(20, 100.0), (3, 110.0), (1, 120.0)]:
            conn.execute(
                "INSERT OR REPLACE INTO price_history(key, ts, value, label) VALUES (?, ?, ?, ?)",
                ("usd", now - offset_days * 86400, value, ""),
            )
        conn.commit()
    finally:
        conn.close()

    week = h.get_history("usd", days=7)
    month = h.get_history("usd", days=30)

    assert len(week) == 2
    assert {p["value"] for p in week} == {110.0, 120.0}
    assert len(month) == 3


def test_prune_removes_old_datapoints(isolated_history):
    h = isolated_history
    import sqlite3

    now = int(time.time())
    conn = sqlite3.connect(h.DB_PATH)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS price_history(key TEXT, ts INTEGER, value REAL, label TEXT, PRIMARY KEY(key, ts))"
        )
        conn.execute(
            "INSERT OR REPLACE INTO price_history VALUES (?, ?, ?, ?)",
            ("oil", now - 100 * 86400, 70.0, ""),
        )
        conn.execute(
            "INSERT OR REPLACE INTO price_history VALUES (?, ?, ?, ?)",
            ("oil", now - 5 * 86400, 80.0, ""),
        )
        conn.commit()
    finally:
        conn.close()

    removed = h.prune(days=60)
    assert removed == 1

    points = h.get_history("oil", days=120)
    assert len(points) == 1
    assert points[0]["value"] == 80.0


def test_get_history_downsamples_large_series(isolated_history):
    h = isolated_history
    import sqlite3

    now = int(time.time())
    conn = sqlite3.connect(h.DB_PATH)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS price_history(key TEXT, ts INTEGER, value REAL, label TEXT, PRIMARY KEY(key, ts))"
        )
        for i in range(500):
            conn.execute(
                "INSERT OR REPLACE INTO price_history VALUES (?, ?, ?, ?)",
                ("dense", now - i * 60, float(i), ""),
            )
        conn.commit()
    finally:
        conn.close()

    points = h.get_history("dense", days=7, limit=50)
    assert len(points) == 50
