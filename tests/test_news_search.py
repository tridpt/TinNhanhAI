"""Tests for cross-topic news search store + endpoint."""

from __future__ import annotations


def _seed(store):
    store.upsert_articles("the_thao", [
        {"url": "https://x/1", "title": "Bóng đá Việt Nam thắng lớn", "summary": "Trận hay", "source": "VnExpress"},
        {"url": "https://x/2", "title": "Tennis quốc tế", "summary": "Giải lớn", "source": "Tuổi Trẻ"},
    ])
    store.upsert_articles("kinh_te", [
        {"url": "https://x/3", "title": "Giá vàng tăng mạnh", "summary": "Vàng SJC", "source": "VnExpress"},
    ])


def test_search_by_keyword(isolated_news_store):
    _seed(isolated_news_store)
    hits = isolated_news_store.search_articles("vàng")
    assert len(hits) == 1
    assert hits[0]["url"] == "https://x/3"


def test_search_by_source(isolated_news_store):
    _seed(isolated_news_store)
    hits = isolated_news_store.search_articles("", source="VnExpress")
    urls = {h["url"] for h in hits}
    assert urls == {"https://x/1", "https://x/3"}


def test_search_by_topic(isolated_news_store):
    _seed(isolated_news_store)
    hits = isolated_news_store.search_articles("", topic="the_thao")
    assert len(hits) == 2


def test_list_sources(isolated_news_store):
    _seed(isolated_news_store)
    assert isolated_news_store.list_sources() == ["Tuổi Trẻ", "VnExpress"]


def test_search_dedups_by_url(isolated_news_store):
    # Same URL under two topics should appear once.
    isolated_news_store.upsert_articles("all", [
        {"url": "https://dup/1", "title": "Tin chung", "summary": "x", "source": "S"},
    ])
    isolated_news_store.upsert_articles("thoi_su", [
        {"url": "https://dup/1", "title": "Tin chung", "summary": "x", "source": "S"},
    ])
    hits = isolated_news_store.search_articles("Tin chung")
    assert len(hits) == 1


def test_search_endpoint_requires_filter(flask_client):
    r = flask_client.get("/api/news/search?q=")
    assert r.status_code == 200
    data = r.get_json()
    assert data["items"] == []
    assert "sources" in data


def test_search_endpoint_returns_matches(flask_client):
    # Seed via the same module the client uses (flask_client already set its DB path).
    from services import news_store

    news_store.upsert_articles("kinh_te", [
        {"url": "https://x/3", "title": "Giá vàng tăng mạnh", "summary": "Vàng SJC", "source": "VnExpress"},
    ])
    r = flask_client.get("/api/news/search?q=vàng")
    assert r.status_code == 200
    data = r.get_json()
    assert data["total"] == 1
    assert data["items"][0]["topic_label"]  # enriched with topic label
