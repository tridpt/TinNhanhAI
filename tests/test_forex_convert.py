"""Tests for amount/currency validation in convert_currency."""

from __future__ import annotations

from unittest.mock import MagicMock


def _resp(payload, status=200):
    r = MagicMock()
    r.status_code = status
    r.raise_for_status = MagicMock()
    r.json = MagicMock(return_value=payload)
    return r


def _stub_rates(monkeypatch):
    from services import vn_prices

    monkeypatch.setattr(
        vn_prices.requests, "get",
        lambda *a, **kw: _resp({"rates": {"VND": 25000.0, "EUR": 0.92}}),
    )


def test_rejects_negative_amount(monkeypatch):
    from services import vn_prices

    _stub_rates(monkeypatch)
    out = vn_prices.convert_currency("USD", "VND", -5)
    assert out["error"] == "invalid amount"
    assert out["status"] == 400


def test_rejects_nan_and_inf(monkeypatch):
    from services import vn_prices

    _stub_rates(monkeypatch)
    assert vn_prices.convert_currency("USD", "VND", float("nan"))["status"] == 400
    assert vn_prices.convert_currency("USD", "VND", float("inf"))["status"] == 400


def test_rejects_absurdly_large_amount(monkeypatch):
    from services import vn_prices

    _stub_rates(monkeypatch)
    out = vn_prices.convert_currency("USD", "VND", 1e15)
    assert out["error"] == "invalid amount"
    assert out["status"] == 400


def test_rejects_junk_amount(monkeypatch):
    from services import vn_prices

    _stub_rates(monkeypatch)
    out = vn_prices.convert_currency("USD", "VND", "abc")
    assert out["error"] == "invalid amount"
    assert out["status"] == 400


def test_rejects_bad_currency_code(monkeypatch):
    from services import vn_prices

    _stub_rates(monkeypatch)
    # Path-injection style and wrong-length codes must be rejected before
    # they reach the upstream URL.
    assert vn_prices.convert_currency("US", "VND", 1)["status"] == 400
    assert vn_prices.convert_currency("USD", "../etc", 1)["status"] == 400
    assert vn_prices.convert_currency("US1", "VND", 1)["status"] == 400


def test_accepts_valid_conversion(monkeypatch):
    from services import vn_prices

    _stub_rates(monkeypatch)
    out = vn_prices.convert_currency("usd", "vnd", 2)
    assert out["rate"] == 25000.0
    assert out["result"] == 50000.0
    assert out["from"] == "USD"
    assert out["to"] == "VND"
