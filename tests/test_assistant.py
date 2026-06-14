"""End-to-end tests for the AI assistant orchestration (answer_question).

Every external dependency (news store, prices, web search, the AI model) is
stubbed so the test exercises only the routing/shaping logic in
``services.assistant``.
"""

from __future__ import annotations

import services.assistant as assistant


def test_empty_question_returns_prompt():
    out = assistant.answer_question("   ")
    assert out["intent"] == "general"
    assert "câu hỏi" in out["answer"].lower()
    assert out["sources"] == []
    assert out["results"] == []


def test_news_intent_routes_to_topic_payload(monkeypatch):
    fake_topic = {
        "label": "Công nghệ",
        "items": [
            {"title": "Tin A", "source": "VnExpress", "url": "https://e/a"},
            {"title": "Tin B", "source": "Tuổi Trẻ", "url": "https://e/b"},
        ],
    }
    monkeypatch.setattr(assistant, "detect_intent", lambda q: {"intent": "news", "topic": "cong_nghe"})
    monkeypatch.setattr(assistant, "get_topic_payload", lambda topic, **kw: fake_topic)
    # AI returns empty → falls back to the deterministic summary.
    monkeypatch.setattr(assistant, "generate_text", lambda *a, **kw: "")

    out = assistant.answer_question("tin công nghệ hôm nay")
    assert out["intent"] == "news"
    assert out["topic"] == "cong_nghe"
    # Fallback news answer lists the titles.
    assert "Tin A" in out["answer"]
    # Sources are deduped from items.
    assert {s["url"] for s in out["sources"]} == {"https://e/a", "https://e/b"}


def test_news_intent_uses_ai_answer_when_available(monkeypatch):
    monkeypatch.setattr(assistant, "detect_intent", lambda q: {"intent": "news", "topic": "all"})
    monkeypatch.setattr(assistant, "get_topic_payload", lambda topic, **kw: {"label": "Tổng hợp", "items": [{"title": "X", "url": "https://e/x"}]})
    monkeypatch.setattr(assistant, "generate_text", lambda *a, **kw: "Câu trả lời AI")

    out = assistant.answer_question("điểm tin")
    assert out["answer"] == "Câu trả lời AI"


def test_commodity_intent_routes_to_prices(monkeypatch):
    fake_prices = {
        "cards": [
            {"label": "Vàng thế giới", "symbol": "GC=F", "price_text": "2,000",
             "change_text": "+1%", "unit": "USD/oz", "source_url": "https://finance.yahoo.com/quote/GC=F"},
        ],
        "vn_cards": [
            {"label": "Vàng SJC", "price_text": "90tr", "unit": "VND",
             "source_url": "https://sjc.com.vn"},
        ],
    }
    monkeypatch.setattr(assistant, "detect_intent", lambda q: {"intent": "commodity", "topic": ""})
    monkeypatch.setattr(assistant, "get_prices_payload", lambda **kw: fake_prices)
    monkeypatch.setattr(assistant, "generate_text", lambda *a, **kw: "")

    out = assistant.answer_question("giá vàng")
    assert out["intent"] == "commodity"
    assert "Vàng thế giới" in out["answer"]
    # Sources include both world + VN cards.
    titles = {s["title"] for s in out["sources"]}
    assert "Vàng thế giới" in titles
    assert "Vàng SJC" in titles


def test_product_intent_routes_to_product_search(monkeypatch):
    fake_search = {
        "results": [
            {"title": "iPhone 15", "url": "https://shop/x", "domain": "shop",
             "price_text": "20.000.000 đ"},
        ],
    }
    monkeypatch.setattr(assistant, "detect_intent", lambda q: {"intent": "product", "topic": ""})
    monkeypatch.setattr(assistant, "search_product_prices", lambda q: fake_search)
    monkeypatch.setattr(assistant, "summarize_search", lambda q, r: "Giá tham khảo")
    monkeypatch.setattr(assistant, "generate_text", lambda *a, **kw: "")

    out = assistant.answer_question("giá iphone 15")
    assert out["intent"] == "product"
    assert out["answer"] == "Giá tham khảo"
    assert out["sources"][0]["url"] == "https://shop/x"


def test_general_intent_routes_to_web_search(monkeypatch):
    fake_search = {"results": [{"title": "Kết quả", "url": "https://w/1", "domain": "w"}]}
    monkeypatch.setattr(assistant, "detect_intent", lambda q: {"intent": "general", "topic": ""})
    monkeypatch.setattr(assistant, "search_general_web", lambda q: fake_search)
    monkeypatch.setattr(assistant, "summarize_search", lambda q, r: "Tóm tắt web")
    monkeypatch.setattr(assistant, "generate_text", lambda *a, **kw: "")

    out = assistant.answer_question("thời tiết sao hỏa thế nào")
    assert out["intent"] == "general"
    assert out["answer"] == "Tóm tắt web"
    assert out["results"] == fake_search["results"]


def test_format_sources_dedupes_and_skips_empty():
    rows = [
        {"title": "A", "url": "https://x/1", "domain": "x"},
        {"title": "A dup", "url": "https://x/1", "domain": "x"},  # duplicate URL
        {"title": "No url"},  # skipped
        {"title": "B", "url": "https://x/2", "domain": "x"},
    ]
    out = assistant._format_sources(rows)
    assert [s["url"] for s in out] == ["https://x/1", "https://x/2"]
