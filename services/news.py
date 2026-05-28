from __future__ import annotations

import calendar
import html
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import feedparser
import requests
from bs4 import BeautifulSoup

import config
from .ai import compact_json, generate_text
from .cache import TTLCache
from .prices import get_prices_payload


UTC = timezone.utc
LOCAL_TZ = timezone(timedelta(hours=7))
CACHE = TTLCache()
USER_AGENT = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TinNhanhAI/1.0"}


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_entry_time(entry: Any) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    ts = calendar.timegm(parsed)
    return datetime.fromtimestamp(ts, tz=UTC).astimezone(LOCAL_TZ)


def _to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _time_label(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.strftime("%d/%m %H:%M")


def _fetch_feed(url: str) -> list[dict[str, Any]]:
    response = requests.get(url, headers=USER_AGENT, timeout=20)
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    items: list[dict[str, Any]] = []
    for entry in feed.entries:
        published_dt = _parse_entry_time(entry)
        items.append(
            {
                "title": _clean_text(entry.get("title")),
                "summary": _clean_text(entry.get("summary") or entry.get("description")),
                "url": entry.get("link") or "",
                "published_at": _to_iso(published_dt),
                "published_label": _time_label(published_dt),
            }
        )
    return items


def _topic_label(topic_key: str) -> str:
    return config.NEWS_TOPIC_META.get(topic_key, {}).get("label", topic_key)


def _topic_icon(topic_key: str) -> str:
    return config.NEWS_TOPIC_META.get(topic_key, {}).get("icon", "newspaper")


def _topic_sources(topic_key: str) -> list[dict[str, str]]:
    if topic_key == "all":
        sources: list[dict[str, str]] = []
        for key in config.NEWS_TOPIC_ORDER:
            if key == "all":
                continue
            sources.extend(config.NEWS_TOPIC_SOURCES.get(key, []))
        return sources
    return config.NEWS_TOPIC_SOURCES.get(topic_key, [])


def _dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in sorted(items, key=lambda row: row.get("published_at") or "", reverse=True):
        key = (item.get("url") or item.get("title") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _collect_topic_items(topic_key: str, limit: int = 6) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for source in _topic_sources(topic_key):
        try:
            fetched = _fetch_feed(source["url"])
        except Exception:
            continue
        for item in fetched[:limit]:
            item = dict(item)
            item["source"] = source["name"]
            item["topic"] = topic_key
            items.append(item)
    return _dedupe_items(items)


def _fallback_summary(label: str, items: list[dict[str, Any]]) -> str:
    if not items:
        return f"Chưa có bài mới cho {label.lower()}."

    top_items = items[:4]
    lines = [f"{label}:", "Điểm nổi bật:"]
    for item in top_items[:3]:
        head = item.get("summary") or item.get("title") or ""
        lines.append(f"- {item.get('title', '').strip()}".rstrip())
        if head and head != item.get("title"):
            lines.append(f"  {head[:180]}")
    return "\n".join(lines)


def _summarize_topic(label: str, items: list[dict[str, Any]]) -> str:
    if not items:
        return f"Chưa có bài mới cho {label.lower()}."

    prompt = f"""
Hãy tóm tắt ngắn gọn chủ đề "{label}" bằng tiếng Việt.
Chỉ dùng dữ liệu bên dưới, không bịa thêm.
Yêu cầu:
- 3 đến 5 gạch đầu dòng
- ngắn, thực dụng, trung lập
- ưu tiên tin nóng nhất

Dữ liệu:
{compact_json(items[:5], limit=4500)}
""".strip()

    text = generate_text(prompt, max_output_tokens=260)
    return text or _fallback_summary(label, items)


def get_topic_payload(topic_key: str, *, force: bool = False) -> dict[str, Any]:
    topic_key = topic_key if topic_key in config.NEWS_TOPIC_META else "all"
    cache_key = f"news-topic:{topic_key}"
    if not force:
        cached = CACHE.get(cache_key)
        if cached:
            return cached

    if topic_key == "all":
        collected: list[dict[str, Any]] = []
        for key in config.NEWS_TOPIC_ORDER:
            if key == "all":
                continue
            collected.extend(_collect_topic_items(key))
        items = _dedupe_items(collected)[:8]
    else:
        items = _collect_topic_items(topic_key)[:8]

    payload = {
        "key": topic_key,
        "label": _topic_label(topic_key),
        "icon": _topic_icon(topic_key),
        "summary": _summarize_topic(_topic_label(topic_key), items),
        "items": items,
        "source_count": len(_topic_sources(topic_key)),
    }
    CACHE.set(cache_key, payload, config.NEWS_REFRESH_SECONDS)
    return payload


def get_dashboard_payload(*, force: bool = False) -> dict[str, Any]:
    cache_key = "dashboard"
    if not force:
        cached = CACHE.get(cache_key)
        if cached:
            return cached

    topics = [get_topic_payload(topic_key, force=force) for topic_key in config.NEWS_TOPIC_ORDER]
    total_items = sum(len(topic["items"]) for topic in topics)
    source_count = sum(topic["source_count"] for topic in topics if topic["key"] != "all")
    top_lines = []
    for topic in topics:
        if topic["key"] == "all":
            continue
        for item in topic["items"][:2]:
            top_lines.append(
                {
                    "topic": topic["label"],
                    "title": item.get("title", ""),
                    "source": item.get("source", ""),
                }
            )
    brief_prompt = f"""
Tóm tắt ngắn gọn bản tin tổng hợp hôm nay bằng tiếng Việt.
Chỉ dựa trên dữ liệu sau, không bịa.
Độ dài: 3 đến 4 câu ngắn.

Dữ liệu:
{compact_json(top_lines[:8], limit=3000)}
""".strip()
    brief = generate_text(brief_prompt, max_output_tokens=220)
    if not brief:
        highlight_titles = [row["title"] for row in top_lines[:4] if row.get("title")]
        brief = " | ".join(highlight_titles) if highlight_titles else "Chưa lấy được đủ dữ liệu tin trong lần tải này."

    payload = {
        "generated_at": datetime.now(LOCAL_TZ).isoformat(),
        "brief": brief,
        "metrics": {
            "topic_count": len([topic for topic in topics if topic["key"] != "all"]),
            "article_count": total_items,
            "source_count": source_count,
        },
        "topics": topics,
        "prices": get_prices_payload(force=force),
    }
    CACHE.set(cache_key, payload, config.DASHBOARD_REFRESH_SECONDS)
    return payload
