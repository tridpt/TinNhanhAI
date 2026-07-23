from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

from flask import Flask

import config
from routes import register_blueprints
from routes.ai import ask_limiter
from services import get_dashboard_payload
from services.ai import ai_enabled
from services.compression import init_compression
from services.logbook import log_event
from services.telegram_alert import start_in_background as start_telegram_watcher

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__, static_folder="frontend", static_url_path="")
register_blueprints(app)
init_compression(app)

# Re-exported for tests and external callers that tweak the limiter.
__all__ = ["app", "ask_limiter"]


def _pick_port(start_port: int) -> int:
    for port in range(start_port, start_port + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((config.HOST, port))
            except OSError:
                continue
            return port
    return start_port


def _print_banner(port: int, mode: str) -> None:
    print("=" * 56)
    print(config.APP_NAME)
    print("=" * 56)
    print(f"Host: http://{config.HOST}:{port}")
    print(f"AI: {'on' if ai_enabled() else 'off'}")
    print(f"Mode: {mode}")
    print("=" * 56)


def _start_prewarm() -> None:
    """Kick off a background thread that pre-fetches dashboard data.

    This ensures the cache is warm by the time the first user hits the page,
    eliminating the 10-15s cold-fetch delay on Fly.io after a deploy/restart.
    """

    import threading

    def _warm():
        try:
            log_event("prewarm", "fetching dashboard")
            get_dashboard_payload(force=True)
            log_event("prewarm", "done")
        except Exception as exc:
            log_event("prewarm", "failed", level="error", error=str(exc))

    thread = threading.Thread(target=_warm, name="prewarm", daemon=True)
    thread.start()


def _run_dev(port: int) -> None:
    _print_banner(port, "dev (Flask)")
    app.run(host=config.HOST, port=port, debug=config.DEBUG)


def _run_prod(port: int) -> None:
    try:
        from waitress import serve
    except ImportError as exc:
        # Fail loudly instead of silently downgrading to the Flask dev server:
        # in production that would swap in a single-threaded server (and the
        # debugger if DEBUG were ever set) without anyone noticing.
        raise RuntimeError(
            "TINNHANH_PROD is set but waitress is not installed. "
            "Install it with `pip install waitress`, or unset TINNHANH_PROD "
            "to run the Flask dev server."
        ) from exc
    _print_banner(port, "prod (waitress)")
    serve(app, host=config.HOST, port=port, threads=8)


if __name__ == "__main__":
    use_prod = os.getenv("TINNHANH_PROD", "").lower() in {"1", "true", "yes"}
    # In production the port is fixed by the platform: Docker EXPOSE, the Fly
    # proxy target and the /api/health check all assume config.PORT. Drifting to
    # another port would leave the app "running" while every health check fails,
    # so bind exactly config.PORT and let the bind error surface. Only dev hunts
    # for a free port to stay convenient across restarts.
    target_port = config.PORT if use_prod else _pick_port(config.PORT)
    if start_telegram_watcher():
        log_event("telegram", "alert watcher enabled")
    from services.price_alert import start_in_background as start_price_watcher

    if start_price_watcher():
        log_event("price-alert", "watcher enabled")
    # Pre-warm caches in background so the first user request is instant.
    _start_prewarm()
    # Server choice is opt-in via TINNHANH_PROD only. DEBUG no longer forces
    # prod mode — it solely controls the (off-by-default) Werkzeug debugger, so
    # a plain ``python app.py`` still gives the Flask dev server with reload.
    if use_prod:
        _run_prod(target_port)
    else:
        _run_dev(target_port)
