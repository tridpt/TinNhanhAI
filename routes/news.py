"""Dashboard and per-topic news feeds."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

import config
from routes import _wants_force
from services import get_dashboard_payload, get_topic_payload

bp = Blueprint("news", __name__)


@bp.get("/api/dashboard")
def dashboard():
    return jsonify(get_dashboard_payload(force=_wants_force(request.args)))


@bp.get("/api/news/<topic>")
def news_topic(topic: str):
    if topic not in config.NEWS_TOPIC_META:
        return jsonify({"error": "unknown_topic", "topic": topic}), 404
    try:
        offset = max(0, int(request.args.get("offset", "0")))
    except ValueError:
        offset = 0
    try:
        limit = max(1, min(int(request.args.get("limit", "20")), 50))
    except ValueError:
        limit = 20
    return jsonify(
        get_topic_payload(topic, force=_wants_force(request.args), offset=offset, limit=limit)
    )
