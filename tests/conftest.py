"""Pytest fixtures shared across the suite.

These fixtures ensure tests run with isolated SQLite history files and
predictable cache state, so the order of tests never matters.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make ``services`` and ``app`` importable when pytest is invoked from CWD.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def isolated_history(tmp_path, monkeypatch):
    """Redirect ``services.history`` to a per-test SQLite file."""

    from services import history

    test_db = tmp_path / "history.db"
    monkeypatch.setattr(history, "DB_PATH", test_db)
    # ``_MIN_INTERVAL_SECONDS = -1`` makes ``cutoff > now`` so the
    # ``last_ts >= cutoff`` guard never fires, effectively disabling the
    # throttle. ``0`` would still allow only one write per second since
    # ``ts`` resolution is whole seconds.
    monkeypatch.setattr(history, "_MIN_INTERVAL_SECONDS", -1)
    yield history


@pytest.fixture()
def fast_rate_limiter():
    """Build a tiny rate limiter for predictable token-bucket assertions."""

    from services.rate_limit import RateLimiter

    return RateLimiter(max_per_minute=3)


@pytest.fixture()
def isolated_news_store(tmp_path, monkeypatch):
    """Redirect ``services.news_store`` to a per-test SQLite file."""

    from services import news_store

    monkeypatch.setattr(news_store, "DB_PATH", tmp_path / "news.db")
    yield news_store


@pytest.fixture()
def isolated_summary_cache(tmp_path, monkeypatch):
    """Redirect ``services.summary_cache`` to a per-test SQLite file."""

    from services import summary_cache

    monkeypatch.setattr(summary_cache, "DB_PATH", tmp_path / "summaries.db")
    yield summary_cache


@pytest.fixture()
def isolated_alerts(tmp_path, monkeypatch):
    """Redirect ``services.alerts`` to a per-test SQLite file."""

    from services import alerts

    monkeypatch.setattr(alerts, "DB_PATH", tmp_path / "alerts.db")
    yield alerts


@pytest.fixture()
def flask_client(monkeypatch, tmp_path):
    """Return a Flask test client with history isolated to ``tmp_path``."""

    from services import history, news_store, summary_cache

    monkeypatch.setattr(history, "DB_PATH", tmp_path / "client_history.db")
    monkeypatch.setattr(history, "_MIN_INTERVAL_SECONDS", -1)
    monkeypatch.setattr(news_store, "DB_PATH", tmp_path / "client_news.db")
    monkeypatch.setattr(summary_cache, "DB_PATH", tmp_path / "client_summaries.db")

    from services import alerts

    monkeypatch.setattr(alerts, "DB_PATH", tmp_path / "client_alerts.db")

    import app as flask_app

    flask_app.app.testing = True
    return flask_app.app.test_client()
