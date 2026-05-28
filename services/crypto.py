"""Live crypto prices from Binance public ticker API.

Uses ``/api/v3/ticker/24hr`` which is free, no auth, and returns the price
plus 24h change percentage in one call. We pick a small set of symbols by
default; users can extend via ``CRYPTO_SYMBOLS`` env var (comma-separated).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import requests

import config

from .cache import TTLCache
from .history import get_history, record_price

LOCAL_TZ = timezone(timedelta(hours=7))
CACHE = TTLCache(namespace="crypto")
HEADERS = {"User-Agent": "Mozilla/5.0 TinNhanhAI/1.0"}
TIMEOUT = 12

# Display metadata for each tracked symbol.
DEFAULT_SYMBOLS: list[dict[str, str]] = [
    {"symbol": "BTCUSDT", "label": "Bitcoin", "icon": "bitcoin"},
    {"symbol": "ETHUSDT", "label": "Ethereum", "icon": "gem"},
    {"symbol": "SOLUSDT", "label": "Solana", "icon": "zap"},
    {"symbol": "BNBUSDT", "label": "BNB", "icon": "shield"},
    {"symbol": "XRPUSDT", "label": "XRP", "icon": "circle-dot"},
    {"symbol": "DOGEUSDT", "label": "Dogecoin", "icon": "dog"},
    {"symbol": "ADAUSDT", "label": "Cardano", "icon": "hexagon"},
    {"symbol": "AVAXUSDT", "label": "Avalanche", "icon": "mountain"},
    {"symbol": "DOTUSDT", "label": "Polkadot", "icon": "circle"},
    {"symbol": "LINKUSDT", "label": "Chainlink", "icon": "link"},
]


def _resolve_symbols() -> list[dict[str, str]]:
    """Allow operators to override the tracked set without code changes."""

    raw = os.getenv("CRYPTO_SYMBOLS", "").strip()
    if not raw:
        return DEFAULT_SYMBOLS
    out: list[dict[str, str]] = []
    for token in raw.split(","):
        symbol = token.strip().upper()
        if not symbol:
            continue
        # Try to keep nice labels for known coins, fall back to the raw symbol.
        match = next(
            (item for item in DEFAULT_SYMBOLS if item["symbol"] == symbol),
            None,
        )
        out.append(
            match
            or {"symbol": symbol, "label": symbol.replace("USDT", ""), "icon": "circle"}
        )
    return out or DEFAULT_SYMBOLS


def _now_label() -> str:
    return datetime.now(LOCAL_TZ).strftime("%d/%m %H:%M")


def fetch_crypto_prices() -> list[dict[str, Any]]:
    """One Binance call for all symbols → list of formatted price cards."""

    specs = _resolve_symbols()
    symbols = [item["symbol"] for item in specs]
    # ``json.dumps`` defaults to ``", "`` separator which Binance rejects;
    # forcing the compact ``,`` matches their regex exactly.
    payload_arg = json.dumps(symbols, separators=(",", ":"))
    url = (
        "https://api.binance.com/api/v3/ticker/24hr?symbols="
        + quote(payload_arg, safe="")
    )
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return []

    if not isinstance(data, list):
        return []

    by_symbol = {row.get("symbol"): row for row in data if isinstance(row, dict)}
    cards: list[dict[str, Any]] = []
    for spec in specs:
        row = by_symbol.get(spec["symbol"])
        if not row:
            continue
        try:
            price = float(row.get("lastPrice"))
            change = float(row.get("priceChange") or 0)
            change_pct = float(row.get("priceChangePercent") or 0)
        except (TypeError, ValueError):
            continue
        cards.append(
            {
                "key": f"crypto_{spec['symbol'].lower()}",
                "label": spec["label"],
                "provider": "Binance",
                "icon": spec["icon"],
                "symbol": spec["symbol"],
                "price": price,
                "change": change,
                "change_percent": change_pct,
                "price_text": _format_usd(price),
                "change_text": _format_change(change, change_pct),
                "unit": "USD",
                "updated_label": _now_label(),
                "source_url": f"https://www.binance.com/en/trade/{spec['symbol']}",
            }
        )
    return cards


def _format_usd(value: float) -> str:
    if value >= 1000:
        return f"{value:,.0f} USD"
    if value >= 1:
        return f"{value:,.2f} USD"
    return f"{value:,.4f} USD"


def _format_change(value: float, percent: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:,.2f} ({sign}{percent:.2f}%)"


def get_crypto_payload(*, force: bool = False) -> dict[str, Any]:
    cache_key = "crypto"
    if not force:
        cached = CACHE.get(cache_key)
        if cached:
            return cached

    cards = fetch_crypto_prices()
    # Fetch 7-day history for sparklines.
    history_map = _fetch_crypto_klines([card["symbol"] for card in cards])
    formatted: list[dict[str, Any]] = []
    for card in cards:
        record_price(card["key"], card.get("price"), label=card["label"])
        own_history = get_history(card["key"])
        kline_history = history_map.get(card["symbol"], [])
        # Use whichever has more points for a richer sparkline.
        history = own_history if len(own_history) >= len(kline_history) else kline_history
        formatted.append({**card, "history": history})

    payload = {
        "generated_at": datetime.now(LOCAL_TZ).isoformat(),
        "cards": formatted,
    }
    CACHE.set(cache_key, payload, config.PRICE_REFRESH_SECONDS)
    return payload


def _fetch_crypto_klines(symbols: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Fetch 7-day daily klines from Binance for sparkline history."""

    result: dict[str, list[dict[str, Any]]] = {}
    for symbol in symbols:
        try:
            response = requests.get(
                "https://api.binance.com/api/v3/klines",
                params={"symbol": symbol, "interval": "4h", "limit": 42},
                headers=HEADERS,
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
        except Exception:
            continue
        if not isinstance(data, list):
            continue
        points = []
        for candle in data:
            # candle[0] = open time ms, candle[4] = close price
            ts = int(candle[0]) // 1000
            close = float(candle[4])
            points.append({"ts": ts, "value": close})
        result[symbol] = points
    return result
