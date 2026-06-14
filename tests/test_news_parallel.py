"""Tests for the parallelized news fetch added during perf work.

These cover that concurrent feed fetching still groups items under the right
topic, dedupes correctly, and fetches each feed at most once per refresh.
"""

from __future__ import annotations

import config
from services import news


def _fake_feed_factory(by_url):
    """Return a stand-in for ``_fetch_feed`` driven by a {url: items} map."""

    def _fake_fetch_feed(url):
        # Mimic the real shape: list of article dicts.
        return list(by_url.get(url, []))

    return _fake_fetch_feed


def test_collect_topic_items_tags_topic_and_source(monkeypatch):
    sources = config.NEWS_TOPIC_SOURCES["cong_nghe"]
    # Give each source one unique article keyed by its URL.
    by_url = {
        src["url"]: [
            {
                "title": f"Tin {src['name']}",
                "summary": "",
                "url": f"{src['url']}#a",
                "published_at": "2026-06-14T08:00:00+07:00",
                "published_label": "14/06 08:00",
                "thumbnail": "",
            }
        ]
        for src in sources
    }
    monkeypatch.setattr(news, "_fetch_feed", _fake_feed_factory(by_url))

    items = news._collect_topic_items("cong_nghe")

    assert len(items) == len(sources)
    # Every item is tagged with the requested topic and a real source name.
    assert all(item["topic"] == "cong_nghe" for item in items)
    source_names = {src["name"] for src in sources}
    assert all(item["source"] in source_names for item in items)


def test_collect_topic_items_dedupes_shared_urls(monkeypatch):
    sources = config.NEWS_TOPIC_SOURCES["the_thao"]
    shared = {
        "title": "Bài trùng",
        "summary": "",
        "url": "https://example.com/dup",
        "published_at": "2026-06-14T08:00:00+07:00",
        "published_label": "14/06 08:00",
        "thumbnail": "",
    }
    # Every source returns the SAME article URL → must collapse to one.
    by_url = {src["url"]: [dict(shared)] for src in sources}
    monkeypatch.setattr(news, "_fetch_feed", _fake_feed_factory(by_url))

    items = news._collect_topic_items("the_thao")
    assert len(items) == 1
    assert items[0]["url"] == "https://example.com/dup"


def test_collect_topic_items_survives_one_failing_feed(monkeypatch):
    sources = config.NEWS_TOPIC_SOURCES["the_thao"]
    good_url = sources[0]["url"]

    def flaky_fetch(url):
        if url != good_url:
            raise RuntimeError("feed down")
        return [
            {
                "title": "Tin tốt",
                "summary": "",
                "url": f"{good_url}#ok",
                "published_at": "2026-06-14T08:00:00+07:00",
                "published_label": "14/06 08:00",
                "thumbnail": "",
            }
        ]

    monkeypatch.setattr(news, "_fetch_feed", flaky_fetch)

    items = news._collect_topic_items("the_thao")
    # All feeds but one raised; the good one still yields its article.
    assert len(items) == 1
    assert items[0]["title"] == "Tin tốt"


def test_refresh_dashboard_topics_fetches_each_feed_once(monkeypatch):
    """The flattened pool must hit each (topic, source) URL exactly once and
    never re-fetch when building the unified ``all`` bucket."""

    fetch_counts: dict[str, int] = {}

    def counting_fetch(url):
        fetch_counts[url] = fetch_counts.get(url, 0) + 1
        return [
            {
                "title": f"Tin {url}",
                "summary": "",
                "url": f"{url}#x",
                "published_at": "2026-06-14T08:00:00+07:00",
                "published_label": "14/06 08:00",
                "thumbnail": "",
            }
        ]

    stored: dict[str, list[dict]] = {}

    def fake_upsert(topic, items):
        stored.setdefault(topic, []).extend(items)
        return len(items)

    # Avoid touching the real TTLCache / SQLite store.
    monkeypatch.setattr(news, "_fetch_feed", counting_fetch)
    monkeypatch.setattr(news.news_store, "upsert_articles", fake_upsert)
    monkeypatch.setattr(news.CACHE, "get", lambda *a, **kw: None)
    monkeypatch.setattr(news.CACHE, "set", lambda *a, **kw: None)

    news._refresh_dashboard_topics(force=True)

    # Build the set of every per-topic source URL.
    all_urls = set()
    for _key, sources in config.NEWS_TOPIC_SOURCES.items():
        for src in sources:
            all_urls.add(src["url"])

    # Each feed URL fetched exactly once despite the "all" bucket being built.
    assert fetch_counts, "no feeds were fetched"
    assert all(count == 1 for count in fetch_counts.values()), fetch_counts
    # The "all" topic was stored (built from already-fetched items, not refetched).
    assert "all" in stored
    assert len(stored["all"]) > 0
