"""Tests for custom watchlist endpoints and weather location."""

from __future__ import annotations

from unittest.mock import MagicMock


def _mock_response(payload, *, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value=payload)
    return response


# --- Custom stocks ---------------------------------------------------------------------


def test_stocks_custom_appends_vn_suffix(flask_client, monkeypatch):
    """Short symbols without a dot should get .VN appended; intl symbols stay."""

    from services import stocks

    captured = []

    def fake_fetch(symbol):
        captured.append(symbol)
        return {
            "price": 25000.0,
            "change": 500.0,
            "change_percent": 2.0,
            "currency": "VND",
            "history": [{"ts": 1, "value": 24500.0}, {"ts": 2, "value": 25000.0}],
        }

    monkeypatch.setattr(stocks, "_fetch_yahoo_stock", fake_fetch)

    response = flask_client.get("/api/stocks/custom?symbols=ACB,AAPL,7203.T")
    assert response.status_code == 200

    # ACB → ACB.VN (short, no dot), AAPL stays (known intl), 7203.T stays (has dot)
    assert "ACB.VN" in captured
    assert "AAPL" in captured
    assert "7203.T" in captured


def test_stocks_custom_uses_currency_from_data(flask_client, monkeypatch):
    from services import stocks

    monkeypatch.setattr(
        stocks,
        "_fetch_yahoo_stock",
        lambda s: {"price": 313500.0, "change": 1000.0, "change_percent": 0.3, "currency": "KRW", "history": []},
    )

    response = flask_client.get("/api/stocks/custom?symbols=005930.KS")
    payload = response.get_json()
    assert payload["cards"][0]["unit"] == "KRW"


def test_stocks_custom_skips_failed_symbol(flask_client, monkeypatch):
    from services import stocks

    monkeypatch.setattr(stocks, "_fetch_yahoo_stock", lambda s: None)

    response = flask_client.get("/api/stocks/custom?symbols=INVALID")
    payload = response.get_json()
    assert payload["cards"] == []


# --- Custom crypto ---------------------------------------------------------------------


def test_crypto_custom_returns_cards(flask_client, monkeypatch):
    import app as flask_app
    from services import crypto

    monkeypatch.setattr(
        crypto,
        "_fetch_crypto_klines",
        lambda symbols: {s: [{"ts": 1, "value": 0.1}, {"ts": 2, "value": 0.11}] for s in symbols},
    )

    # Patch requests.get used inside the endpoint.
    fake_tickers = [
        {"symbol": "DOGEUSDT", "lastPrice": "0.11", "priceChange": "0.01", "priceChangePercent": "10.0"},
    ]
    monkeypatch.setattr(
        flask_app.__dict__.get("requests", None) or __import__("requests"),
        "get",
        lambda *a, **kw: _mock_response(fake_tickers),
    )

    response = flask_client.get("/api/crypto/custom?symbols=DOGEUSDT")
    assert response.status_code == 200
    payload = response.get_json()
    assert len(payload["cards"]) == 1
    assert payload["cards"][0]["symbol"] == "DOGEUSDT"
    assert "USD" in payload["cards"][0]["price_text"]


# --- Weather location ------------------------------------------------------------------


def test_weather_location_requires_coords(flask_client):
    response = flask_client.get("/api/weather/location")
    assert response.status_code == 400


def test_weather_location_returns_forecast(flask_client, monkeypatch):
    import requests as req

    fake_payload = {
        "current": {
            "temperature_2m": 30.0,
            "apparent_temperature": 33.0,
            "relative_humidity_2m": 70,
            "weather_code": 2,
            "wind_speed_10m": 5.0,
        },
        "daily": {
            "time": ["2026-05-29", "2026-05-30"],
            "weather_code": [2, 61],
            "temperature_2m_max": [33.0, 31.0],
            "temperature_2m_min": [26.0, 25.0],
            "precipitation_probability_max": [20, 80],
        },
        "hourly": {
            "time": ["2026-05-29T00:00", "2026-05-29T03:00", "2026-05-30T00:00"],
            "temperature_2m": [27.0, 26.5, 25.0],
            "weather_code": [2, 2, 61],
            "precipitation_probability": [10, 15, 80],
        },
    }
    monkeypatch.setattr(req, "get", lambda *a, **kw: _mock_response(fake_payload))

    response = flask_client.get("/api/weather/location?lat=10.76&lon=106.66&name=Test City")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["city"] == "Test City"
    assert payload["temperature_text"] == "30°C"
    assert len(payload["forecast"]) == 2
    # First day should have 2 hourly entries.
    assert len(payload["forecast"][0]["hours"]) == 2


# --- Forex convert route ---------------------------------------------------------------


def test_forex_convert_route_success(flask_client, monkeypatch):
    from services import vn_prices

    monkeypatch.setattr(
        vn_prices.requests,
        "get",
        lambda *a, **kw: _mock_response({"rates": {"VND": 25000.0}}),
    )
    response = flask_client.get("/api/forex/convert?from=USD&to=VND&amount=3")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["rate"] == 25000.0
    assert payload["result"] == 75000.0


def test_forex_convert_route_bad_target(flask_client, monkeypatch):
    from services import vn_prices

    monkeypatch.setattr(
        vn_prices.requests,
        "get",
        lambda *a, **kw: _mock_response({"rates": {"VND": 25000.0}}),
    )
    response = flask_client.get("/api/forex/convert?from=USD&to=ZZZ&amount=1")
    assert response.status_code == 400


def test_forex_custom_route_empty_codes(flask_client):
    response = flask_client.get("/api/forex/custom?codes=")
    assert response.status_code == 200
    assert response.get_json()["cards"] == []
