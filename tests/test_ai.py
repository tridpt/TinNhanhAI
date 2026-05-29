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


def test_compact_json_truncates_long_data():
    from services.ai import compact_json

    big = [{"key": "x" * 100} for _ in range(100)]
    result = compact_json(big, limit=500)
    assert len(result) <= 500
    assert "rút gọn" in result
