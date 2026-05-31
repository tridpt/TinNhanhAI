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
            print("[prewarm] fetching dashboard...")
            get_dashboard_payload(force=True)
            print("[prewarm] done")
        except Exception as exc:
            print(f"[prewarm] failed: {exc}")

    thread = threading.Thread(target=_warm, name="prewarm", daemon=True)
    thread.start()


def _run_dev(port: int) -> None:
    _print_banner(port, "dev (Flask)")
    app.run(host=config.HOST, port=port, debug=config.DEBUG)


def _run_prod(port: int) -> None:
    try:
        from waitress import serve
    except ImportError:
        print("waitress is not installed; falling back to Flask dev server.")
        _run_dev(port)
        return
    _print_banner(port, "prod (waitress)")
    serve(app, host=config.HOST, port=port, threads=8)


if __name__ == "__main__":
    target_port = _pick_port(config.PORT)
    if start_telegram_watcher():
        print("[telegram] alert watcher enabled")
    from services.price_alert import start_in_background as start_price_watcher

    if start_price_watcher():
        print("[price-alert] watcher enabled")
    # Pre-warm caches in background so the first user request is instant.
    _start_prewarm()
    use_prod = os.getenv("TINNHANH_PROD", "").lower() in {"1", "true", "yes"} or not config.DEBUG
    if use_prod:
        _run_prod(target_port)
    else:
        _run_dev(target_port)
