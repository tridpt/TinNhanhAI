"""Tests for intent detection and helper utilities in services/search.py."""

from __future__ import annotations

import pytest

from services.search import _is_plausible_price, _strip_accents, detect_intent


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Việt Nam", "viet nam"),
        ("Bảo Tín Minh Châu", "bao tin minh chau"),
        ("ĐỒNG", "đong"),  # 'đ' is not a combining mark; only diacritics strip
        ("plain ascii", "plain ascii"),
    ],
)
def test_strip_accents(text, expected):
    # Lower-case to match the way the production code uses _strip_accents.
    assert _strip_accents(text).lower() == expected


@pytest.mark.parametrize(
    "question, intent",
    [
        ("Tóm tắt tin công nghệ hôm nay", "news"),
        ("Điểm tin nóng hôm nay", "news"),
        ("Giá vàng hiện tại", "commodity"),
        ("USD hôm nay bao nhiêu", "commodity"),
        ("Tỷ giá ngân hàng", "commodity"),
        ("Giá xăng dầu thế nào", "commodity"),
        ("Giá iPhone 15 Pro Max", "product"),
        ("Mua laptop gaming nào tốt", "product"),
        ("Thủ tục đăng ký kết hôn ở Việt Nam", "general"),
    ],
)
def test_detect_intent(question, intent):
    result = detect_intent(question)
    assert result["intent"] == intent


@pytest.mark.parametrize(
    "question, topic",
    [
        ("Tóm tắt tin công nghệ hôm nay", "cong_nghe"),
        ("Điểm tin kinh tế chứng khoán", "kinh_te"),
        ("Tin thế giới hôm nay", "the_gioi"),
        ("Tin thể thao bóng đá", "the_thao"),
        ("Bản tin thời sự", "thoi_su"),
        ("Bản tin tổng hợp hôm nay", "all"),
    ],
)
def test_detect_intent_picks_news_topic(question, topic):
    result = detect_intent(question)
    assert result["intent"] == "news"
    assert result["topic"] == topic


@pytest.mark.parametrize(
    "value, currency, expected",
    [
        (None, "VND", False),
        (5_000.0, "VND", False),  # too small
        (50_000.0, "VND", True),
        (0.5, "USD", False),
        (1.0, "USD", True),
        (1500.0, "USD", True),
    ],
)
def test_is_plausible_price(value, currency, expected):
    assert _is_plausible_price(value, currency) is expected



def test_price_domain_allowlist_matches_config():
    """Adding a retailer to config.RETAIL_SEARCH_SITES must not orphan the search filter."""

    import config
    from services.search import PRICE_DOMAIN_ALLOWLIST

    expected = tuple(item["domain"] for item in config.RETAIL_SEARCH_SITES)
    assert set(PRICE_DOMAIN_ALLOWLIST) == set(expected)
    assert len(PRICE_DOMAIN_ALLOWLIST) == len(config.RETAIL_SEARCH_SITES)
