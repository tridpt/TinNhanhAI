"""AI-powered endpoints: ask, read article, summarize (rate-limited)."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

import config
from services import answer_question
from services.rate_limit import RateLimiter, limit

bp = Blueprint("ai", __name__)

# Shared per-IP rate limiter for AI calls (ask + summarize cache-misses).
ask_limiter = RateLimiter(config.ASK_RATE_LIMIT_PER_MINUTE)


@bp.post("/api/ask")
@limit(ask_limiter)
def ask():
    payload = request.get_json(silent=True) or {}
    question = str(payload.get("question", "")).strip()
    if not question:
        return jsonify({"error": "question is required"}), 400
    return jsonify(answer_question(question))


@bp.post("/api/read")
@limit(ask_limiter)
def read_article():
    """Extract article content from a URL for inline reading.

    Rate-limited per IP because it fetches an external URL on the caller's
    behalf — without a cap it could be abused as an open fetch proxy.
    """

    from services.reader import fetch_article

    payload = request.get_json(silent=True) or {}
    url = str(payload.get("url", "")).strip()
    if not url:
        return jsonify({"error": "url is required"}), 400
    return jsonify(fetch_article(url))


@bp.post("/api/summarize")
def summarize_article():
    """Summarize article text with AI, cached by content hash.

    Cache hits bypass the rate limiter entirely since they cost no AI quota;
    only genuine AI calls (cache misses) are rate-limited.
    """

    from services.ai import ai_enabled, generate_text
    from services.summary_cache import get_summary, save_summary

    payload = request.get_json(silent=True) or {}
    title = str(payload.get("title", "")).strip()
    content = str(payload.get("content", "")).strip()

    if not content:
        return jsonify({"error": "content is required"}), 400

    # Serve from cache first — an article's text never changes, so a cached
    # summary is always valid and saves a Gemini call (and free-tier quota).
    cached = get_summary(title, content)
    if cached:
        return jsonify({"summary": cached, "cached": True})

    if not ai_enabled():
        return jsonify({
            "summary": "",
            "error": "ai_disabled",
            "message": "Chưa bật AI. Đặt GEMINI_API_KEY để dùng tính năng này.",
        })

    # Only a real AI call counts against the rate limit.
    allowed, retry_after = ask_limiter.check()
    if not allowed:
        response = jsonify({
            "summary": "",
            "error": "rate_limited",
            "message": "Bạn đang tóm tắt quá nhanh, hãy thử lại sau.",
            "retry_after": retry_after,
        })
        response.status_code = 429
        response.headers["Retry-After"] = str(retry_after)
        return response

    # Truncate very long articles to keep prompt within limits.
    text = content[:6000]
    prompt = f"""
Hãy tóm tắt bài báo sau bằng tiếng Việt, ngắn gọn 3-5 gạch đầu dòng.
Nêu ý chính, số liệu quan trọng nếu có. Không bịa thêm.

Tiêu đề: {title}

Nội dung:
{text}
""".strip()

    summary = generate_text(prompt, max_output_tokens=400)
    if not summary:
        return jsonify({
            "summary": "",
            "error": "ai_failed",
            "message": "AI đang quá tải, thử lại sau.",
        })
    # Cache the fresh summary for next time.
    save_summary(title, content, summary)
    return jsonify({"summary": summary, "cached": False})
