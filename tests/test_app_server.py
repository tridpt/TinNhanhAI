"""Tests for the server bootstrap behaviour in ``app.py``.

Covers the two production-safety guarantees added when the dev/prod split was
hardened:

1. In production the port is fixed to ``config.PORT`` (never auto-drifts), while
   dev still hunts for a free port.
2. ``_run_prod`` fails loudly if waitress is missing instead of silently falling
   back to the Flask dev server.
"""

from __future__ import annotations

import socket
import sys

import pytest

import app as flask_app
import config


def test_resolve_port_prod_binds_exact_port(monkeypatch):
    """Production must return config.PORT verbatim and never scan for a free one."""

    monkeypatch.setattr(config, "PORT", 8080)

    def _boom(_start):  # pragma: no cover - only runs on regression
        raise AssertionError("prod must not hunt for a free port")

    monkeypatch.setattr(flask_app, "_pick_port", _boom)

    assert flask_app._resolve_port(use_prod=True) == 8080


def test_resolve_port_dev_hunts_for_free_port(monkeypatch):
    """Dev delegates to _pick_port so restarts stay convenient."""

    monkeypatch.setattr(config, "PORT", 5055)
    monkeypatch.setattr(flask_app, "_pick_port", lambda start: start + 7)

    assert flask_app._resolve_port(use_prod=False) == 5062


def test_pick_port_skips_an_occupied_port(monkeypatch):
    """When the start port is taken, _pick_port advances to the next free one."""

    monkeypatch.setattr(config, "HOST", "127.0.0.1")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.bind(("127.0.0.1", 0))  # let the OS assign a free port
        occupied.listen(1)
        taken_port = occupied.getsockname()[1]

        chosen = flask_app._pick_port(taken_port)

    assert chosen != taken_port
    assert taken_port < chosen <= taken_port + 20


def test_run_prod_raises_when_waitress_missing(monkeypatch):
    """Missing waitress must raise, not silently start the Flask dev server."""

    # Force ``from waitress import serve`` to raise ImportError.
    monkeypatch.setitem(sys.modules, "waitress", None)

    # Guard: if the fail-fast broke and it fell through to dev, this would fire.
    monkeypatch.setattr(flask_app.app, "run", lambda *a, **k: pytest.fail("must not start dev server"))

    with pytest.raises(RuntimeError, match="waitress"):
        flask_app._run_prod(8080)


def test_run_prod_serves_with_waitress(monkeypatch):
    """With waitress available, _run_prod hands the app to serve() on the port."""

    waitress = pytest.importorskip("waitress")

    captured: dict[str, object] = {}

    def fake_serve(wsgi_app, **kwargs):
        captured["app"] = wsgi_app
        captured.update(kwargs)

    monkeypatch.setattr(waitress, "serve", fake_serve)

    flask_app._run_prod(1234)

    assert captured["app"] is flask_app.app
    assert captured["port"] == 1234
    assert captured["host"] == config.HOST
    assert captured["threads"] == 8
