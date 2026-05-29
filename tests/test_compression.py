"""Tests for the gzip compression after_request hook."""

from __future__ import annotations

import gzip


def test_json_response_is_gzipped_when_large(flask_client, monkeypatch):
    # Seed enough articles so the search payload exceeds the gzip threshold.
    from services import news_store

    big = [
        {
            "url": f"https://x/{i}",
            "title": "Tiêu đề bài báo số " + str(i) * 10,
            "summary": "Nội dung tóm tắt khá dài để vượt ngưỡng nén " * 5,
            "source": "VnExpress",
        }
        for i in range(60)
    ]
    news_store.upsert_articles("thoi_su", big)

    res = flask_client.get(
        "/api/news/search?q=bài", headers={"Accept-Encoding": "gzip"}
    )
    assert res.status_code == 200
    assert res.headers.get("Content-Encoding") == "gzip"
    # Body must be valid gzip that decodes back to JSON.
    decoded = gzip.decompress(res.data)
    assert b"items" in decoded


def test_small_response_not_gzipped(flask_client):
    # Health payload is tiny — below the 1KB threshold, so it stays raw.
    res = flask_client.get("/api/health", headers={"Accept-Encoding": "gzip"})
    assert res.status_code == 200
    assert res.headers.get("Content-Encoding") is None


def test_no_gzip_without_accept_encoding(flask_client):
    from services import news_store

    news_store.upsert_articles("thoi_su", [
        {"url": "https://x/1", "title": "T" * 50, "summary": "S" * 2000, "source": "VnExpress"},
    ])
    # Werkzeug's test client sends Accept-Encoding by default; override to empty.
    res = flask_client.get("/api/news/search?q=T", headers={"Accept-Encoding": ""})
    assert res.status_code == 200
    assert res.headers.get("Content-Encoding") is None
