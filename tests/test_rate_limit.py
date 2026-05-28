"""Tests for the per-IP token bucket used by /api/ask."""

from __future__ import annotations

import pytest
from flask import Flask

from services.rate_limit import RateLimiter, limit


@pytest.fixture()
def limited_app():
    """Mount a tiny Flask app behind a 3-per-minute limiter."""

    app = Flask(__name__)
    limiter = RateLimiter(max_per_minute=3)

    @app.post("/ping")
    @limit(limiter)
    def ping():
        return {"pong": True}

    return app, limiter


def test_allows_up_to_max_requests(limited_app):
    app, _ = limited_app
    client = app.test_client()

    statuses = [client.post("/ping").status_code for _ in range(3)]
    assert statuses == [200, 200, 200]


def test_blocks_after_limit(limited_app):
    app, _ = limited_app
    client = app.test_client()

    for _ in range(3):
        client.post("/ping")
    response = client.post("/ping")
    assert response.status_code == 429

    payload = response.get_json()
    assert payload["error"] == "rate_limited"
    assert payload["retry_after"] >= 1
    assert "Retry-After" in response.headers


def test_separate_clients_get_independent_buckets(limited_app):
    app, _ = limited_app
    client = app.test_client()

    for _ in range(3):
        client.post("/ping", environ_base={"REMOTE_ADDR": "1.2.3.4"})
    blocked = client.post("/ping", environ_base={"REMOTE_ADDR": "1.2.3.4"})
    fresh = client.post("/ping", environ_base={"REMOTE_ADDR": "9.8.7.6"})

    assert blocked.status_code == 429
    assert fresh.status_code == 200


def test_x_forwarded_for_used_when_present(limited_app):
    app, _ = limited_app
    client = app.test_client()

    headers = {"X-Forwarded-For": "203.0.113.10, 10.0.0.1"}
    for _ in range(3):
        client.post("/ping", headers=headers)
    response = client.post("/ping", headers=headers)
    assert response.status_code == 429


def test_window_resets_when_oldest_hit_expires(limited_app, monkeypatch):
    app, limiter = limited_app
    import services.rate_limit as rl

    fake_now = [1_700_000_000.0]
    monkeypatch.setattr(rl.time, "time", lambda: fake_now[0])

    client = app.test_client()
    for _ in range(3):
        client.post("/ping")
    assert client.post("/ping").status_code == 429

    # Advance past the 60s window.
    fake_now[0] += 61
    assert client.post("/ping").status_code == 200
