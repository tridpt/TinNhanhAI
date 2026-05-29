"""Tests for the AI summary cache store and the /api/summarize endpoint."""

from __future__ import annotations

from unittest.mock import MagicMock


def test_make_key_is_stable_and_content_sensitive():
    from services import summary_cache

    k1 = summary_cache.make_key("Tiêu đề", "Nội dung bài báo")
    k2 = summary_cache.make_key("Tiêu đề", "Nội dung bài báo")
    k3 = summary_cache.make_key("Tiêu đề", "Nội dung khác")
    assert k1 == k2
    assert k1 != k3


def test_get_returns_none_when_empty(isolated_summary_cache):
    assert isolated_summary_cache.get_summary("T", "C") is None


def test_save_and_get_roundtrip(isolated_summary_cache):
    isolated_summary_cache.save_summary("T", "C", "Tóm tắt nội dung")
    assert isolated_summary_cache.get_summary("T", "C") == "Tóm tắt nội dung"


def test_save_ignores_blank_summary(isolated_summary_cache):
    isolated_summary_cache.save_summary("T", "C", "   ")
    assert isolated_summary_cache.get_summary("T", "C") is None


def test_summarize_endpoint_caches_after_first_call(flask_client, monkeypatch):
    """First call hits the AI; second identical call is served from cache."""

    import config
    from services import ai

    monkeypatch.setattr(config, "GEMINI_API_KEY", "gkey")

    calls = {"n": 0}

    def fake_post(*a, **kw):
        calls["n"] += 1
        resp = MagicMock()
        resp.status_code = 200
        resp.json = MagicMock(return_value={
            "candidates": [{"content": {"parts": [{"text": "Tóm tắt AI"}]}}]
        })
        return resp

    monkeypatch.setattr(ai.requests, "post", fake_post)

    body = {"title": "Bài báo", "content": "Nội dung dài để tóm tắt."}

    r1 = flask_client.post("/api/summarize", json=body)
    assert r1.status_code == 200
    data1 = r1.get_json()
    assert data1["summary"] == "Tóm tắt AI"
    assert data1["cached"] is False
    assert calls["n"] == 1

    r2 = flask_client.post("/api/summarize", json=body)
    assert r2.status_code == 200
    data2 = r2.get_json()
    assert data2["summary"] == "Tóm tắt AI"
    assert data2["cached"] is True
    # No additional AI call was made the second time.
    assert calls["n"] == 1


def test_summarize_requires_content(flask_client):
    r = flask_client.post("/api/summarize", json={"title": "x", "content": ""})
    assert r.status_code == 400


def test_summarize_rate_limited_returns_retry_info(flask_client, monkeypatch):
    """A rate-limited cache-miss returns 429 with retry metadata for the UI."""

    import app as flask_app
    import config
    from services import ai

    monkeypatch.setattr(config, "GEMINI_API_KEY", "gkey")
    monkeypatch.setattr(flask_app.ask_limiter, "max_per_minute", 1)
    # Reset the shared limiter's buckets so prior tests don't affect counts.
    flask_app.ask_limiter._hits.clear()

    def fake_post(*a, **kw):
        resp = MagicMock()
        resp.status_code = 200
        resp.json = MagicMock(return_value={
            "candidates": [{"content": {"parts": [{"text": "ok"}]}}]
        })
        return resp

    monkeypatch.setattr(ai.requests, "post", fake_post)

    # First unique article consumes the only token.
    r1 = flask_client.post("/api/summarize", json={"title": "a", "content": "noi dung 1"})
    assert r1.status_code == 200
    # Second unique article (cache miss) is rate limited.
    r2 = flask_client.post("/api/summarize", json={"title": "b", "content": "noi dung 2"})
    assert r2.status_code == 429
    data = r2.get_json()
    assert data["error"] == "rate_limited"
    assert "retry_after" in data
    assert data["message"]


def test_summarize_cache_hit_bypasses_rate_limit(flask_client, monkeypatch):
    """Cache hits must not be blocked by the rate limiter (no AI cost)."""

    import app as flask_app
    import config
    from services import ai

    monkeypatch.setattr(config, "GEMINI_API_KEY", "gkey")

    def fake_post(*a, **kw):
        resp = MagicMock()
        resp.status_code = 200
        resp.json = MagicMock(return_value={
            "candidates": [{"content": {"parts": [{"text": "Tóm tắt"}]}}]
        })
        return resp

    monkeypatch.setattr(ai.requests, "post", fake_post)
    flask_app.ask_limiter._hits.clear()

    body = {"title": "z", "content": "noi dung cache"}
    # Warm the cache with one allowed call.
    assert flask_client.post("/api/summarize", json=body).status_code == 200
    # Now choke the limiter; cache hit should still succeed.
    monkeypatch.setattr(flask_app.ask_limiter, "max_per_minute", 1)
    flask_client.post("/api/summarize", json={"title": "q", "content": "tieu hao token"})
    r = flask_client.post("/api/summarize", json=body)
    assert r.status_code == 200
    assert r.get_json()["cached"] is True
