from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

import config
from services import answer_question, get_dashboard_payload, get_prices_payload, get_topic_payload
from services.ai import ai_enabled
from services.rate_limit import RateLimiter, limit
from services.telegram_alert import start_in_background as start_telegram_watcher

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__, static_folder="frontend", static_url_path="")
ask_limiter = RateLimiter(config.ASK_RATE_LIMIT_PER_MINUTE)


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


@app.get("/")
def index():
    return send_from_directory("frontend", "index.html")


@app.get("/manifest.webmanifest")
def manifest():
    response = send_from_directory("frontend", "manifest.webmanifest")
    response.headers["Content-Type"] = "application/manifest+json"
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


@app.get("/sw.js")
def service_worker():
    """Serve the service worker from the root scope.

    Browsers tie a service worker's scope to the directory of its script URL,
    so the file must live at ``/sw.js`` (not under ``/static/sw.js``) for it
    to control the whole origin. ``Service-Worker-Allowed`` is sent for
    completeness even though the script already sits at root.
    """

    response = send_from_directory("frontend", "sw.js")
    response.headers["Content-Type"] = "application/javascript"
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/icons/<path:filename>")
def icons(filename: str):
    return send_from_directory("frontend/icons", filename)


@app.get("/api/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "app_name": config.APP_NAME,
            "ai_enabled": ai_enabled(),
            "openai_model": config.OPENAI_MODEL if ai_enabled() else "",
        }
    )


@app.get("/api/dashboard")
def dashboard():
    force = request.args.get("force", "0").lower() in {"1", "true", "yes"}
    return jsonify(get_dashboard_payload(force=force))


@app.get("/api/news/<topic>")
def news_topic(topic: str):
    if topic not in config.NEWS_TOPIC_META:
        return jsonify({"error": "unknown_topic", "topic": topic}), 404
    force = request.args.get("force", "0").lower() in {"1", "true", "yes"}
    return jsonify(get_topic_payload(topic, force=force))


@app.get("/api/prices")
def prices():
    force = request.args.get("force", "0").lower() in {"1", "true", "yes"}
    return jsonify(get_prices_payload(force=force))


@app.get("/api/crypto")
def crypto():
    from services.crypto import get_crypto_payload

    force = request.args.get("force", "0").lower() in {"1", "true", "yes"}
    return jsonify(get_crypto_payload(force=force))


@app.get("/api/stocks")
def stocks():
    from services.stocks import get_stocks_payload

    force = request.args.get("force", "0").lower() in {"1", "true", "yes"}
    return jsonify(get_stocks_payload(force=force))


@app.get("/api/weather")
def weather():
    from services.weather import get_weather_payload

    force = request.args.get("force", "0").lower() in {"1", "true", "yes"}
    return jsonify(get_weather_payload(force=force))


@app.get("/api/prices/history")
def prices_history():
    from services.history import get_history

    key = request.args.get("key", "").strip()
    if not key:
        return jsonify({"error": "key is required"}), 400
    try:
        days = max(1, min(int(request.args.get("days", "7")), 60))
    except ValueError:
        days = 7
    return jsonify({"key": key, "days": days, "points": get_history(key, days=days)})


@app.post("/api/ask")
@limit(ask_limiter)
def ask():
    payload = request.get_json(silent=True) or {}
    question = str(payload.get("question", "")).strip()
    if not question:
        return jsonify({"error": "question is required"}), 400
    return jsonify(answer_question(question))


@app.get("/favicon.ico")
def favicon():
    return ("", 204)


def _print_banner(port: int, mode: str) -> None:
    print("=" * 56)
    print(config.APP_NAME)
    print("=" * 56)
    print(f"Host: http://{config.HOST}:{port}")
    print(f"AI: {'on' if ai_enabled() else 'off'}")
    print(f"Mode: {mode}")
    print("=" * 56)


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
    use_prod = os.getenv("TINNHANH_PROD", "").lower() in {"1", "true", "yes"} or not config.DEBUG
    if use_prod:
        _run_prod(target_port)
    else:
        _run_dev(target_port)
