"""Tests for the persistent news article store (accumulation + pagination)."""

from __future__ import annotations


def _make_items(count, *, prefix="art", topic_ts_base=1_700_000_000):
    return [
        {
            "url": f"https://example.com/{prefix}-{i}",
            "title": f"Bài {i}",
            "summary": f"Tóm tắt {i}",
            "source": "TestSource",
            "thumbnail": "",
            "published_at": f"2026-05-{(i % 28) + 1:02d}T08:00:00+07:00",
            "published_label": f"{(i % 28) + 1:02d}/05 08:00",
        }
        for i in range(count)
    ]


def test_upsert_inserts_new_and_skips_duplicates(isolated_news_store):
    store = isolated_news_store
    items = _make_items(5)

    first = store.upsert_articles("thoi_su", items)
    assert first == 5

    # Re-inserting the same items adds nothing.
    second = store.upsert_articles("thoi_su", items)
    assert second == 0

    assert store.count_articles("thoi_su") == 5


def test_accumulation_keeps_old_articles(isolated_news_store):
    """New refreshes add to the store without removing old articles."""

    store = isolated_news_store
    store.upsert_articles("kinh_te", _make_items(5, prefix="old"))
    store.upsert_articles("kinh_te", _make_items(5, prefix="new"))

    # 10 distinct URLs accumulated.
    assert store.count_articles("kinh_te") == 10


def test_cap_prunes_oldest_over_limit(isolated_news_store, monkeypatch):
    store = isolated_news_store
    monkeypatch.setattr(store, "MAX_ARTICLES_PER_TOPIC", 10)

    store.upsert_articles("cong_nghe", _make_items(15, prefix="batch"))

    # Capped at 10.
    assert store.count_articles("cong_nghe") == 10


def test_pagination_offset_limit(isolated_news_store):
    store = isolated_news_store
    store.upsert_articles("the_thao", _make_items(25))

    page1 = store.get_articles("the_thao", offset=0, limit=10)
    page2 = store.get_articles("the_thao", offset=10, limit=10)
    page3 = store.get_articles("the_thao", offset=20, limit=10)

    assert len(page1) == 10
    assert len(page2) == 10
    assert len(page3) == 5

    # No overlap between pages.
    urls1 = {a["url"] for a in page1}
    urls2 = {a["url"] for a in page2}
    assert urls1.isdisjoint(urls2)


def test_empty_items_returns_zero(isolated_news_store):
    store = isolated_news_store
    assert store.upsert_articles("all", []) == 0
    assert store.count_articles("all") == 0


def test_articles_without_url_are_skipped(isolated_news_store):
    store = isolated_news_store
    items = [{"url": "", "title": "No URL"}, {"url": "https://ok.com/1", "title": "OK"}]
    inserted = store.upsert_articles("thoi_su", items)
    assert inserted == 1
    assert store.count_articles("thoi_su") == 1
