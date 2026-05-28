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
    with patch("app.answer_question", return_value=fake_response) as mock_answer:
        response = flask_client.post("/api/ask", json={"question": "hello"})

    assert response.status_code == 200
    assert response.get_json()["answer"] == "stubbed"
    mock_answer.assert_called_once_with("hello")
