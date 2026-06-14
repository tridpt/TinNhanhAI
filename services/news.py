from __future__ import annotations

import calendar
import html
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import feedparser
import requests
from bs4 import BeautifulSoup

import config

from . import news_store
from .ai import compact_json, generate_text
from .cache import TTLCache
from .crypto import get_crypto_payload
from .prices import get_prices_payload
from .stocks import get_stocks_payload
from .weather import get_weather_payload

UTC = UTC
LOCAL_TZ = timezone(timedelta(hours=7))
CACHE = TTLCache(namespace="news")
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
    response = requests.get(url, headers=USER_AGENT, timeout=10)
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    items: list[dict[str, Any]] = []
    for entry in feed.entries:
        published_dt = _parse_entry_time(entry)
        thumbnail = _extract_thumbnail(entry)
        items.append(
            {
                "title": _clean_text(entry.get("title")),
                "summary": _clean_text(entry.get("summary") or entry.get("description")),
                "url": entry.get("link") or "",
                "published_at": _to_iso(published_dt),
                "published_label": _time_label(published_dt),
                "thumbnail": thumbnail,
            }
        )
    return items


def _extract_thumbnail(entry: Any) -> str:
    """Best-effort thumbnail URL from RSS entry metadata."""

    # <enclosure url="..." type="image/...">
    for enc in getattr(entry, "enclosures", []) or []:
        url = enc.get("href") or enc.get("url") or ""
        enc_type = enc.get("type") or ""
        if url and ("image" in enc_type or url.endswith((".jpg", ".jpeg", ".png", ".webp"))):
            return url

    # <media:content url="..."> or <media:thumbnail url="...">
    media = entry.get("media_content") or entry.get("media_thumbnail") or []
    if isinstance(media, list):
        for item in media:
            url = item.get("url") or ""
            if url:
                return url

    # Some feeds put image in description HTML
    desc = entry.get("summary") or entry.get("description") or ""
    if "<img" in desc:
        import re as _re

        match = _re.search(r'<img[^>]+src=["\']([^"\']+)["\']', desc)
        if match:
            return match.group(1)

    return ""


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


def _fetch_source_items(topic_key: str, source: dict[str, str], limit: int = 15) -> list[dict[str, Any]]:
    """Fetch one feed and tag each item with its topic/source. Never raises."""

    try:
        fetched = _fetch_feed(source["url"])
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for item in fetched[:limit]:
        item = dict(item)
        item["source"] = source["name"]
        item["topic"] = topic_key
        out.append(item)
    return out


def _collect_topic_items(topic_key: str, limit: int = 15) -> list[dict[str, Any]]:
    sources = _topic_sources(topic_key)
    if not sources:
        return []

    # Fetch every source concurrently — feeds are independent network calls,
    # so doing them serially made the dashboard wait on the sum of all latencies
    # (and any slow/timeout feed). A bounded thread pool keeps it to roughly the
    # slowest single feed instead.
    items: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(8, len(sources))) as pool:
        for batch in pool.map(lambda src: _fetch_source_items(topic_key, src, limit), sources):
            items.extend(batch)
    return _dedupe_items(items)


def _fallback_summary(label: str, items: list[dict[str, Any]]) -> str:
    if not items:
        return f"Chưa có bài mới cho {label.lower()}."

    titles = [item.get("title", "").strip() for item in items[:4] if item.get("title")]
    return " | ".join(titles) if titles else f"Đang cập nhật {label.lower()}..."


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


def get_topic_payload(topic_key: str, *, force: bool = False, offset: int = 0, limit: int = 20) -> dict[str, Any]:
    topic_key = topic_key if topic_key in config.NEWS_TOPIC_META else "all"

    # On force refresh (or first load), fetch fresh RSS and store new articles.
    cache_key = f"news-topic-fetched:{topic_key}"
    if force or not CACHE.get(cache_key):
        if topic_key == "all":
            collected: list[dict[str, Any]] = []
            for key in config.NEWS_TOPIC_ORDER:
                if key == "all":
                    continue
                fresh = _collect_topic_items(key)
                news_store.upsert_articles(key, fresh)
                collected.extend(fresh)
            # Also store under "all" topic for unified pagination.
            deduped = _dedupe_items(collected)
            news_store.upsert_articles("all", deduped)
        else:
            fresh = _collect_topic_items(topic_key)
            news_store.upsert_articles(topic_key, fresh)
        CACHE.set(cache_key, True, config.NEWS_REFRESH_SECONDS)

    # Always read from persistent store (accumulated articles).
    items = news_store.get_articles(topic_key, offset=offset, limit=limit)
    total = news_store.count_articles(topic_key)

    # Generate AI summary only for the "all" topic to conserve API quota.
    # Other topics use a lightweight fallback (titles) unless cached.
    summary = ""
    if offset == 0:
        summary_cache_key = f"news-summary:{topic_key}"
        summary = CACHE.get(summary_cache_key) or ""
        if not summary:
            if topic_key == "all":
                # Only the main feed gets an AI summary by default.
                summary = _summarize_topic(_topic_label(topic_key), items[:8])
            else:
                summary = _fallback_summary(_topic_label(topic_key), items)
            CACHE.set(summary_cache_key, summary, config.NEWS_REFRESH_SECONDS)

    return {
        "key": topic_key,
        "label": _topic_label(topic_key),
        "icon": _topic_icon(topic_key),
        "summary": summary,
        "items": items,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + limit < total,
        "source_count": len(_topic_sources(topic_key)),
    }


def _refresh_dashboard_topics(force: bool) -> None:
    """Fetch every topic's feeds in a single shared thread pool, then store
    them (including the unified ``all`` bucket).

    Two layers of waste used to dominate cold refreshes:

    1. The ``all`` branch re-fetched every per-topic feed a second time.
    2. Topics were refreshed serially, so total time was the *sum* of each
       topic's fetch — ~50s across 10 topics.

    Here we flatten every (topic, source) pair that still needs a refresh into
    one pool, so wall time is roughly the slowest single feed. Items are then
    grouped back per topic, stored, and reused to build ``all`` — each feed is
    hit at most once.
    """

    pending: list[tuple[str, dict[str, str]]] = []
    for key in config.NEWS_TOPIC_ORDER:
        if key == "all":
            continue
        topic_cache_key = f"news-topic-fetched:{key}"
        if not force and CACHE.get(topic_cache_key):
            continue
        for source in _topic_sources(key):
            pending.append((key, source))

    if not pending:
        return

    by_topic: dict[str, list[dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=min(16, len(pending))) as pool:
        batches = pool.map(lambda pair: _fetch_source_items(pair[0], pair[1]), pending)
        for (topic_key, _source), batch in zip(pending, batches, strict=False):
            by_topic.setdefault(topic_key, []).extend(batch)

    collected: list[dict[str, Any]] = []
    for key, raw_items in by_topic.items():
        deduped = _dedupe_items(raw_items)
        news_store.upsert_articles(key, deduped)
        collected.extend(deduped)
        CACHE.set(f"news-topic-fetched:{key}", True, config.NEWS_REFRESH_SECONDS)

    all_cache_key = "news-topic-fetched:all"
    if collected and (force or not CACHE.get(all_cache_key)):
        news_store.upsert_articles("all", _dedupe_items(collected))
        CACHE.set(all_cache_key, True, config.NEWS_REFRESH_SECONDS)


def get_dashboard_payload(*, force: bool = False) -> dict[str, Any]:
    """Return the dashboard payload, served stale-while-revalidate.

    A force refresh always rebuilds synchronously. Otherwise we serve the last
    payload immediately and, if it is older than ``DASHBOARD_REFRESH_SECONDS``,
    kick off a single background rebuild so the next request gets fresh data —
    the user never waits on the ~15-25s cold fetch.
    """

    if force:
        payload = _build_dashboard_payload(force=True)
        # Seed the SWR wrapper too so the next non-force read sees it as fresh.
        CACHE.set("dashboard", {"v": payload, "ts": datetime.now().timestamp()},
                  config.DASHBOARD_REFRESH_SECONDS * 4)
        return payload

    return CACHE.get_or_set_swr(
        "dashboard",
        lambda: _build_dashboard_payload(force=False),
        fresh_seconds=config.DASHBOARD_REFRESH_SECONDS,
    )


def _build_dashboard_payload(*, force: bool = False) -> dict[str, Any]:
    # The five data sources (news RSS, prices, crypto, stocks, weather) are
    # independent network calls. Running them serially made the cold refresh
    # take the *sum* of their latencies (~50s). Launch them together so the
    # wall time is roughly the slowest single source instead.
    with ThreadPoolExecutor(max_workers=5) as pool:
        news_future = pool.submit(_refresh_dashboard_topics, force)
        prices_future = pool.submit(_safe_payload, get_prices_payload, force=force)
        crypto_future = pool.submit(_safe_payload, get_crypto_payload, force=force)
        stocks_future = pool.submit(_safe_payload, get_stocks_payload, force=force)
        weather_future = pool.submit(_safe_payload, get_weather_payload, force=force)
        news_future.result()  # ensure feeds are stored before reading them back
        prices_payload = prices_future.result()
        crypto_payload = crypto_future.result()
        stocks_payload = stocks_future.result()
        weather_payload = weather_future.result()

    # Feeds are already stored, so read each topic straight from SQLite.
    topics = [get_topic_payload(topic_key, force=False) for topic_key in config.NEWS_TOPIC_ORDER]
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
        "prices": prices_payload,
        "crypto": crypto_payload,
        "stocks": stocks_payload,
        "weather": weather_payload,
    }
    return payload


def _safe_payload(builder, *, force: bool):
    """Run a payload builder but never let a single source break the dashboard."""

    try:
        return builder(force=force)
    except Exception:
        return {"error": "fetch_failed"}
