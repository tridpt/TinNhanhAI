"""Static shell, PWA assets, and health check."""

from __future__ import annotations

from flask import Blueprint, jsonify, send_from_directory

import config
from services.ai import ai_enabled, ai_provider

bp = Blueprint("pages", __name__)


@bp.get("/")
def index():
    return send_from_directory("frontend", "index.html")


@bp.get("/manifest.webmanifest")
def manifest():
    response = send_from_directory("frontend", "manifest.webmanifest")
    response.headers["Content-Type"] = "application/manifest+json"
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


@bp.get("/sw.js")
def service_worker():
    """Serve the service worker from the root scope.

    Browsers tie a service worker's scope to the directory of its script URL,
    so the file must live at ``/sw.js`` (not under ``/static/sw.js``) for it
    to control the whole origin.
    """

    response = send_from_directory("frontend", "sw.js")
    response.headers["Content-Type"] = "application/javascript"
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response


@bp.get("/icons/<path:filename>")
def icons(filename: str):
    return send_from_directory("frontend/icons", filename)


@bp.get("/favicon.ico")
def favicon():
    return ("", 204)


@bp.get("/api/health")
def health():
    provider = ai_provider()
    model = ""
    if provider == "gemini":
        model = config.GEMINI_MODEL
    elif provider == "openai":
        model = config.OPENAI_MODEL

    from services.price_alert import watcher_status as price_watcher_status
    from services.telegram_alert import watcher_status as telegram_watcher_status

    return jsonify(
        {
            "status": "ok",
            "app_name": config.APP_NAME,
            "ai_enabled": ai_enabled(),
            "ai_provider": provider,
            "ai_model": model,
            "watchers": {
                "telegram": telegram_watcher_status(),
                "price_alert": price_watcher_status(),
            },
        }
    )
