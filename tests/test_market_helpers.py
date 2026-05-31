"""Tests for market formatting/normalisation helpers added during refactor."""

from __future__ import annotations

from unittest.mock import MagicMock


def _resp(payload, status=200):
    r = MagicMock()
    r.status_code = status
    r.raise_for_status = MagicMock()
    r.json = MagicMock(return_value=payload)
    return r


# --- crypto formatting -------------------------------------------------------


def test_format_usd_by_magnitude():
    from services.crypto import _format_usd

    assert _format_usd(73000.5) == "73,001 USD" or _format_usd(73000.5) == "73,000 USD"
    assert _format_usd(2.5) == "2.50 USD"
    assert _format_usd(0.0234).startswith("0.0234")


def test_format_usd_tiny_coin_keeps_significant_digits():
    from services.crypto import _format_usd

    text = _format_usd(0.00000531)
    # Must not collapse to 0.00 — should reveal significant digits.
    assert text not in ("0.00 USD", "0 USD")
    assert "0.0000053" in text


def test_format_change_signs():
    from services.crypto import _format_change

    assert _format_change(120.5, 2.1) == "+120.50 (+2.10%)"
    assert _format_change(-3.2, -1.5) == "-3.20 (-1.50%)"
    # Mixed: negative percent, tiny positive value.
    out = _format_change(0.00045, -7.84)
    assert out.endswith("(-7.84%)")
    assert out.startswith("+")


# --- stock symbol normalisation ----------------------------------------------


def test_normalize_stock_symbol():
    from services.stocks import _normalize_stock_symbol

    assert _normalize_stock_symbol("fpt") == "FPT.VN"      # bare VN ticker
    assert _normalize_stock_symbol("AAPL") == "AAPL"        # known intl
    assert _normalize_stock_symbol("7203.T") == "7203.T"    # explicit suffix
    assert _normalize_stock_symbol("GOOGL") == "GOOGL"      # known intl


def test_get_custom_stock_cards_filters_missing(monkeypatch):
    from services import stocks

    def fake_fetch(symbol):
        if symbol == "FPT.VN":
            return {"price": 120000.0, "change": 1000.0, "change_percent": 0.8,
                    "currency": "VND", "history": []}
        return None  # unknown symbol

    monkeypatch.setattr(stocks, "_fetch_yahoo_stock", fake_fetch)
    cards = stocks.get_custom_stock_cards(["FPT", "ZZZZ"])
    assert len(cards) == 1
    assert cards[0]["symbol"] == "FPT.VN"
    assert cards[0]["unit"] == "VND"


# --- currency convert --------------------------------------------------------


def test_convert_currency_success(monkeypatch):
    from services import vn_prices

    monkeypatch.setattr(
        vn_prices.requests, "get",
        lambda *a, **kw: _resp({"rates": {"VND": 25000.0, "EUR": 0.92}}),
    )
    out = vn_prices.convert_currency("USD", "VND", 2)
    assert out["rate"] == 25000.0
    assert out["result"] == 50000.0
    assert "USD" in out["result_text"]


def test_convert_currency_unknown_target(monkeypatch):
    from services import vn_prices

    monkeypatch.setattr(
        vn_prices.requests, "get",
        lambda *a, **kw: _resp({"rates": {"VND": 25000.0}}),
    )
    out = vn_prices.convert_currency("USD", "ZZZ", 1)
    assert out["error"]
    assert out["status"] == 400


def test_convert_currency_network_failure(monkeypatch):
    from services import vn_prices

    def boom(*a, **kw):
        raise vn_prices.requests.RequestException("down")

    monkeypatch.setattr(vn_prices.requests, "get", boom)
    out = vn_prices.convert_currency("USD", "VND", 1)
    assert out["error"] == "fetch_failed"
    assert out["status"] == 502


# --- VN number parsing -------------------------------------------------------


def test_parse_vn_number_handles_formats():
    from services.vn_prices import _parse_vn_number

    assert _parse_vn_number("1.234.567") == 1234567.0   # thousand separators
    assert _parse_vn_number("26.143,00") == 26143.0     # vn decimal comma
    assert _parse_vn_number("92,5") == 92.5             # decimal comma
    assert _parse_vn_number("") is None
    assert _parse_vn_number("abc") is None
