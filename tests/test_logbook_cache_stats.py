"""Tests for structured logging and cache hit/miss metrics."""

from __future__ import annotations

import json

from services.cache import TTLCache


def test_log_event_json_mode(capsys, monkeypatch):
    from services import logbook

    monkeypatch.setenv("LOG_JSON", "1")
    logbook.log_event("telegram", "sent alerts", count=3)
    out = capsys.readouterr().out.strip()
    record = json.loads(out)
    assert record["tag"] == "telegram"
    assert record["msg"] == "sent alerts"
    assert record["count"] == 3
    assert record["level"] == "info"
    assert "ts" in record


def test_log_event_plain_mode(capsys, monkeypatch):
    from services import logbook

    monkeypatch.setenv("LOG_JSON", "0")
    logbook.log_event("prewarm", "done", duration=1.2)
    out = capsys.readouterr().out.strip()
    assert out == "[prewarm] done duration=1.2"


def test_log_event_error_goes_to_stderr(capsys, monkeypatch):
    from services import logbook

    monkeypatch.setenv("LOG_JSON", "1")
    logbook.log_event("price-alert", "scan failed", level="error", error="boom")
    captured = capsys.readouterr()
    assert captured.out.strip() == ""  # nothing on stdout
    record = json.loads(captured.err.strip())
    assert record["level"] == "error"
    assert record["error"] == "boom"


def test_cache_stats_counts_hits_and_misses():
    cache = TTLCache(namespace="stats-test", persist=False)

    before = TTLCache.stats()
    cache.get("absent")  # miss
    cache.set("k", "v", ttl_seconds=60)
    cache.get("k")  # hit
    after = TTLCache.stats()

    assert after["misses"] >= before["misses"] + 1
    assert after["hits"] >= before["hits"] + 1
    assert 0.0 <= after["hit_rate"] <= 1.0
