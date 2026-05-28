"""Tests for the new market data services: crypto, stocks, weather."""

from __future__ import annotations

from unittest.mock import MagicMock


def _mock_response(payload, *, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value=payload)
    return response


# --- Crypto ----------------------------------------------------------------------------


def test_crypto_url_uses_compact_json(monkeypatch):
    """Binance rejects the default ``json.dumps`` whitespace; verify we strip it."""

    from services import crypto

    captured = {}

    def fake_get(url, *args, **kwargs):
        captured["url"] = url
        return _mock_response([
            {"symbol": "BTCUSDT", "lastPrice": "100", "priceChange": "1", "priceChangePercent": "1"},
        ])

    monkeypatch.setattr(crypto.requests, "get", fake_get)
    crypto.fetch_crypto_prices()

    assert "url" in captured
    # Compact json.dumps gives `["BTCUSDT","ETHUSDT"]`, urlencoded as
    # %5B%22BTCUSDT%22%2C%22ETHUSDT%22%5D — no %20 (space) anywhere.
    assert "%20" not in captured["url"], f"URL contains a space: {captured['url']}"


def test_crypto_parses_price_payload(monkeypatch):
    from services import crypto

    fake_payload = [
        {
            "symbol": "BTCUSDT",
            "lastPrice": "73000.50",
            "priceChange": "-1500.5",
            "priceChangePercent": "-2.0",
        },
        {
            "symbol": "ETHUSDT",
            "lastPrice": "2000.00",
            "priceChange": "50.0",
            "priceChangePercent": "2.5",
        },
    ]
    monkeypatch.setattr(crypto.requests, "get", lambda *a, **kw: _mock_response(fake_payload))

    cards = crypto.fetch_crypto_prices()
    bitcoin = next(card for card in cards if card["symbol"] == "BTCUSDT")
    ethereum = next(card for card in cards if card["symbol"] == "ETHUSDT")

    assert bitcoin["price"] == 73000.5
    assert bitcoin["change"] == -1500.5
    assert bitcoin["change_percent"] == -2.0
    assert "USD" in bitcoin["price_text"]
    # Format chosen per magnitude: ≥1000 → no decimals.
    assert bitcoin["price_text"].startswith("73,000") or bitcoin["price_text"].startswith("73,001")
    assert ethereum["price"] == 2000.0
    assert ethereum["change_text"].startswith("+50.00")


def test_crypto_returns_empty_on_failure(monkeypatch):
    from services import crypto

    def boom(*args, **kwargs):
        raise crypto.requests.RequestException("nope")

    monkeypatch.setattr(crypto.requests, "get", boom)
    assert crypto.fetch_crypto_prices() == []


def test_crypto_resolve_symbols_env_override(monkeypatch):
    from services import crypto

    monkeypatch.setenv("CRYPTO_SYMBOLS", "BTCUSDT, DOGEUSDT")
    specs = crypto._resolve_symbols()
    assert [item["symbol"] for item in specs] == ["BTCUSDT", "DOGEUSDT"]
    # Known coin keeps its display label, unknown gets a fallback derived from the symbol.
    assert next(item for item in specs if item["symbol"] == "DOGEUSDT")["label"] == "DOGE"


# --- Stocks ----------------------------------------------------------------------------


def test_stocks_parse_dchart_history(monkeypatch):
    from services import stocks

    payload = {
        "s": "ok",
        "t": [1716854400, 1716940800, 1717027200],
        "c": [1200.5, 1210.0, 1215.7],
        "o": [1190, 1200, 1208],
        "h": [1215, 1220, 1218],
        "l": [1185, 1198, 1206],
    }
    monkeypatch.setattr(stocks.requests, "get", lambda *a, **kw: _mock_response(payload))

    snapshot = stocks._fetch_index_history("VNINDEX")
    assert snapshot is not None
    assert snapshot["last_close"] == 1215.7
    assert snapshot["prev_close"] == 1210.0
    assert round(snapshot["change"], 1) == 5.7
    assert len(snapshot["session_history"]) == 3


def test_stocks_returns_none_when_endpoint_says_no_data(monkeypatch):
    from services import stocks

    monkeypatch.setattr(
        stocks.requests,
        "get",
        lambda *a, **kw: _mock_response({"s": "no_data"}),
    )
    assert stocks._fetch_index_history("ANYTHING") is None


# --- Weather ---------------------------------------------------------------------------


def test_weather_describes_known_codes():
    from services.weather import _describe_code

    assert _describe_code(0) == ("Trời quang", "sun")
    assert _describe_code(63) == ("Mưa", "cloud-rain")
    assert _describe_code(95) == ("Dông", "cloud-lightning")
    # Unknown codes fall back gracefully.
    assert _describe_code(999) == ("Thời tiết", "cloud")
    assert _describe_code(None) == ("Chưa rõ", "cloud")


def test_weather_skips_failed_city(monkeypatch):
    from services import weather

    call_count = {"n": 0}

    def fake_get(url, *args, **kwargs):
        call_count["n"] += 1
        # Fail the first city but return valid data for the rest.
        if call_count["n"] == 1:
            raise weather.requests.RequestException("rate limited")
        return _mock_response({
            "current": {
                "temperature_2m": 30.5,
                "apparent_temperature": 33.0,
                "relative_humidity_2m": 70,
                "weather_code": 2,
                "wind_speed_10m": 5.2,
                "time": "2026-05-28T14:00",
            }
        })

    monkeypatch.setattr(weather.requests, "get", fake_get)

    cards = weather.fetch_weather()
    # 3 cities total, first failed → 2 cards returned.
    assert len(cards) == 2
    assert cards[0]["temperature_text"] == "30°C"
    assert cards[0]["humidity_text"] == "70%"
