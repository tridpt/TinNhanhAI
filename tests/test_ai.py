"""Tests for AI provider selection and text extraction."""

from __future__ import annotations

from unittest.mock import MagicMock


def test_provider_prefers_gemini(monkeypatch):
    import config
    from services import ai

    monkeypatch.setattr(config, "GEMINI_API_KEY", "gkey")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "okey")
    assert ai.ai_provider() == "gemini"


def test_provider_openai_when_no_gemini(monkeypatch):
    import config
    from services import ai

    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "okey")
    assert ai.ai_provider() == "openai"


def test_provider_none_when_no_keys(monkeypatch):
    import config
    from services import ai

    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    assert ai.ai_provider() == "none"
    assert ai.ai_enabled() is False


def test_extract_gemini_text():
    from services.ai import _extract_gemini_text

    data = {
        "candidates": [
            {"content": {"parts": [{"text": "Xin chào"}, {"text": " thế giới"}]}}
        ]
    }
    assert _extract_gemini_text(data) == "Xin chào\n thế giới"


def test_extract_gemini_text_empty():
    from services.ai import _extract_gemini_text

    assert _extract_gemini_text({}) == ""
    assert _extract_gemini_text({"candidates": []}) == ""


def test_generate_text_returns_empty_without_provider(monkeypatch):
    import config
    from services import ai

    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    assert ai.generate_text("test") == ""


def test_generate_text_uses_gemini(monkeypatch):
    import config
    from services import ai

    monkeypatch.setattr(config, "GEMINI_API_KEY", "gkey")

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.raise_for_status = MagicMock()
    fake_resp.json = MagicMock(return_value={
        "candidates": [{"content": {"parts": [{"text": "Tóm tắt AI"}]}}]
    })
    monkeypatch.setattr(ai.requests, "post", lambda *a, **kw: fake_resp)

    result = ai.generate_text("Tóm tắt tin")
    assert result == "Tóm tắt AI"


def test_generate_text_falls_back_on_429(monkeypatch):
    """When the primary model is rate-limited, a fallback model is tried."""

    import config
    from services import ai

    monkeypatch.setattr(config, "GEMINI_API_KEY", "gkey")
    monkeypatch.setattr(config, "GEMINI_MODEL", "gemini-2.5-flash")

    calls: list[str] = []

    def fake_post(url, *a, **kw):
        calls.append(url)
        resp = MagicMock()
        # First call (primary model) returns 429, subsequent ones succeed.
        if len(calls) == 1:
            resp.status_code = 429
            resp.json = MagicMock(return_value={})
        else:
            resp.status_code = 200
            resp.json = MagicMock(return_value={
                "candidates": [{"content": {"parts": [{"text": "Fallback OK"}]}}]
            })
        return resp

    monkeypatch.setattr(ai.requests, "post", fake_post)

    result = ai.generate_text("Tóm tắt tin")
    assert result == "Fallback OK"
    assert len(calls) >= 2  # primary + at least one fallback


def test_generate_text_gives_up_on_500(monkeypatch):
    """A non-429 error should not trigger fallback retries."""

    import config
    from services import ai

    monkeypatch.setattr(config, "GEMINI_API_KEY", "gkey")

    calls: list[str] = []

    def fake_post(url, *a, **kw):
        calls.append(url)
        resp = MagicMock()
        resp.status_code = 500
        resp.json = MagicMock(return_value={})
        return resp

    monkeypatch.setattr(ai.requests, "post", fake_post)

    result = ai.generate_text("Tóm tắt tin")
    assert result == ""
    assert len(calls) == 1  # gave up after first non-429 error


def test_compact_json_truncates_long_data():
    from services.ai import compact_json

    big = [{"key": "x" * 100} for _ in range(100)]
    result = compact_json(big, limit=500)
    assert len(result) <= 500
    assert "rút gọn" in result
