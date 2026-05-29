"""End-to-end style tests against the Flask app via test_client."""

from __future__ import annotations

from unittest.mock import patch


def test_health_endpoint(flask_client):
    response = flask_client.get("/api/health")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["app_name"]
    assert "ai_enabled" in payload
    assert "ai_provider" in payload


def test_ask_requires_question(flask_client):
    response = flask_client.post("/api/ask", json={})

    assert response.status_code == 400
    assert response.get_json()["error"] == "question is required"


def test_history_endpoint_requires_key(flask_client):
    response = flask_client.get("/api/prices/history")
    assert response.status_code == 400


def test_history_endpoint_returns_points(flask_client, monkeypatch):
    from services import history

    fake_now = [1_700_000_000]

    def fake_time():
        fake_now[0] += 1
        return fake_now[0]

    monkeypatch.setattr(history.time, "time", fake_time)

    history.record_price("test_key", 100.0, label="Test")
    history.record_price("test_key", 101.0, label="Test")

    response = flask_client.get("/api/prices/history?key=test_key&days=7")
    assert response.status_code == 200

    payload = response.get_json()
    assert payload["key"] == "test_key"
    assert payload["days"] == 7
    assert len(payload["points"]) == 2


def test_history_endpoint_clamps_days(flask_client):
    """``days`` must stay between 1 and 60."""

    response = flask_client.get("/api/prices/history?key=anything&days=999")
    payload = response.get_json()
    assert payload["days"] == 60

    response = flask_client.get("/api/prices/history?key=anything&days=-3")
    payload = response.get_json()
    assert payload["days"] == 1

    response = flask_client.get("/api/prices/history?key=anything&days=abc")
    payload = response.get_json()
    assert payload["days"] == 7  # falls back to default


def test_ask_runs_through_assistant(flask_client):
    """Stub the assistant so the endpoint can be tested without network calls."""

    from app import ask_limiter

    # Reset the limiter so this test isn't affected by previous runs.
    ask_limiter._hits.clear()

    fake_response = {
        "intent": "news",
        "topic": "all",
        "answer": "stubbed",
        "sources": [],
        "results": [],
        "generated_at": "2026-01-01T00:00:00+07:00",
    }
    with patch("routes.ai.answer_question", return_value=fake_response) as mock_answer:
        response = flask_client.post("/api/ask", json={"question": "hello"})

    assert response.status_code == 200
    assert response.get_json()["answer"] == "stubbed"
    mock_answer.assert_called_once_with("hello")



def test_manifest_endpoint(flask_client):
    response = flask_client.get("/manifest.webmanifest")

    assert response.status_code == 200
    assert response.headers["Content-Type"] == "application/manifest+json"
    payload = response.get_json()
    assert payload["name"] == "TinNhanh AI"
    assert payload["start_url"] == "/"
    assert payload["display"] == "standalone"


def test_service_worker_endpoint(flask_client):
    response = flask_client.get("/sw.js")

    assert response.status_code == 200
    assert "javascript" in response.headers["Content-Type"]
    # Allowed scope must be the root so the SW can control the whole origin.
    assert response.headers["Service-Worker-Allowed"] == "/"
    body = response.data.decode("utf-8")
    assert "tinnhanh-v" in body
    assert "fetch" in body  # the SW exports a fetch listener
    # Cache-Control should let the browser pick up new versions quickly.
    assert "no-cache" in response.headers.get("Cache-Control", "")


def test_icons_endpoint(flask_client):
    response = flask_client.get("/icons/icon.svg")
    assert response.status_code == 200
    assert "svg" in response.headers["Content-Type"]



def test_news_topic_returns_404_for_unknown_topic(flask_client):
    response = flask_client.get("/api/news/banana")

    assert response.status_code == 404
    payload = response.get_json()
    assert payload["error"] == "unknown_topic"
    assert payload["topic"] == "banana"


def test_news_topic_accepts_known_topic(flask_client, monkeypatch):
    """Smoke check that valid topics still hit the payload builder."""

    import routes.news as news_routes

    monkeypatch.setattr(
        news_routes,
        "get_topic_payload",
        lambda topic, *, force=False, offset=0, limit=20: {"key": topic, "items": [], "label": "stub", "total": 0, "offset": 0, "limit": 20, "has_more": False},
    )

    response = flask_client.get("/api/news/all")
    assert response.status_code == 200
    assert response.get_json()["key"] == "all"
