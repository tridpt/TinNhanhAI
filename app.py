from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

import config
from services import answer_question, get_dashboard_payload, get_prices_payload, get_topic_payload
from services.ai import ai_enabled


sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__, static_folder="frontend", static_url_path="")


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
    force = request.args.get("force", "0").lower() in {"1", "true", "yes"}
    return jsonify(get_topic_payload(topic, force=force))


@app.get("/api/prices")
def prices():
    force = request.args.get("force", "0").lower() in {"1", "true", "yes"}
    return jsonify(get_prices_payload(force=force))


@app.post("/api/ask")
def ask():
    payload = request.get_json(silent=True) or {}
    question = str(payload.get("question", "")).strip()
    if not question:
        return jsonify({"error": "question is required"}), 400
    return jsonify(answer_question(question))


@app.get("/favicon.ico")
def favicon():
    return ("", 204)


if __name__ == "__main__":
    port = _pick_port(config.PORT)
    print("=" * 56)
    print(config.APP_NAME)
    print("=" * 56)
    print(f"Host: http://{config.HOST}:{port}")
    print(f"AI: {'on' if ai_enabled() else 'off'}")
    print("=" * 56)
    app.run(host=config.HOST, port=port, debug=config.DEBUG)

