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


@bp.get("/api/news/search")
def news_search():
    """Search across all stored articles by keyword, topic, and source."""

    from services.news_store import list_sources, search_articles

    query = request.args.get("q", "").strip()
    topic = request.args.get("topic", "").strip() or None
    source = request.args.get("source", "").strip() or None

    if topic and topic not in config.NEWS_TOPIC_META:
        topic = None

    try:
        limit = max(1, min(int(request.args.get("limit", "40")), 100))
    except ValueError:
        limit = 40

    # Require at least one filter so we don't dump the whole store.
    if not (query or topic or source):
        return jsonify({"items": [], "total": 0, "sources": list_sources()})

    items = search_articles(query, topic=topic, source=source, limit=limit)
    for item in items:
        meta = config.NEWS_TOPIC_META.get(item.get("topic", ""), {})
        item["topic_label"] = meta.get("label", "")
    return jsonify({
        "items": items,
        "total": len(items),
        "query": query,
        "sources": list_sources(),
    })


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
