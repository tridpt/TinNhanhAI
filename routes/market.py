"""Market data: prices, crypto, stocks, forex, weather, price history."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from routes import _wants_force
from services import get_prices_payload

bp = Blueprint("market", __name__)


# --- Prices (gold, oil, VN commodities) --------------------------------------


@bp.get("/api/prices")
def prices():
    return jsonify(get_prices_payload(force=_wants_force(request.args)))


@bp.get("/api/prices/history")
def prices_history():
    from services.history import get_history

    key = request.args.get("key", "").strip()
    if not key:
        return jsonify({"error": "key is required"}), 400
    try:
        days = max(1, min(int(request.args.get("days", "7")), 60))
    except ValueError:
        days = 7
    return jsonify({"key": key, "days": days, "points": get_history(key, days=days)})


# --- Crypto ------------------------------------------------------------------


@bp.get("/api/crypto")
def crypto():
    from services.crypto import get_crypto_payload

    return jsonify(get_crypto_payload(force=_wants_force(request.args)))


@bp.get("/api/crypto/custom")
def crypto_custom():
    from services.crypto import get_custom_crypto_cards

    raw = request.args.get("symbols", "")
    symbols = [s for s in raw.split(",") if s.strip()]
    return jsonify({"cards": get_custom_crypto_cards(symbols)})


# --- Stocks ------------------------------------------------------------------


@bp.get("/api/stocks")
def stocks():
    from services.stocks import get_stocks_payload

    return jsonify(get_stocks_payload(force=_wants_force(request.args)))


@bp.get("/api/stocks/custom")
def stocks_custom():
    from services.stocks import get_custom_stock_cards

    raw = request.args.get("symbols", "")
    symbols = [s for s in raw.split(",") if s.strip()]
    return jsonify({"cards": get_custom_stock_cards(symbols)})


# --- Forex -------------------------------------------------------------------


@bp.get("/api/forex/custom")
def forex_custom():
    from services.vn_prices import get_custom_forex_cards

    raw = request.args.get("codes", "")
    codes = [c for c in raw.split(",") if c.strip()]
    result = get_custom_forex_cards(codes)
    if result.get("error"):
        return jsonify({"cards": [], "error": result["error"]}), 502
    return jsonify(result)


@bp.get("/api/forex/convert")
def forex_convert():
    from services.vn_prices import convert_currency

    result = convert_currency(
        request.args.get("from", "USD"),
        request.args.get("to", "VND"),
        request.args.get("amount", "1"),
    )
    if result.get("error"):
        status = result.pop("status", 502)
        return jsonify(result), status
    return jsonify(result)


# --- Weather -----------------------------------------------------------------


@bp.get("/api/weather")
def weather():
    from services.weather import get_weather_payload

    return jsonify(get_weather_payload(force=_wants_force(request.args)))


@bp.get("/api/weather/location")
def weather_location():
    from services.weather import fetch_location_weather

    result = fetch_location_weather(
        request.args.get("lat"),
        request.args.get("lon"),
        request.args.get("name", "Vị trí của bạn"),
    )
    if result.get("error"):
        status = result.pop("status", 502)
        return jsonify(result), status
    return jsonify(result)
