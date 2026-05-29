"""Vietnamese stock indices via VNDirect's public dchart endpoint."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

import config

from .cache import TTLCache
from .history import get_history, record_price

LOCAL_TZ = timezone(timedelta(hours=7))
CACHE = TTLCache(namespace="stocks")
HEADERS = {"User-Agent": "Mozilla/5.0 TinNhanhAI/1.0"}
TIMEOUT = 12

INDICES = [
    {"symbol": "VNINDEX", "label": "VN-Index", "icon": "trending-up"},
    {"symbol": "HNXIndex", "label": "HNX-Index", "icon": "activity"},
    {"symbol": "UPCOM", "label": "UPCOM", "icon": "line-chart"},
]

# Top VN stocks tracked via Yahoo Finance (suffix .VN).
VN_STOCKS = [
    {"symbol": "FPT.VN", "label": "FPT Corp", "icon": "cpu"},
    {"symbol": "VNM.VN", "label": "Vinamilk", "icon": "milk"},
    {"symbol": "HPG.VN", "label": "Hòa Phát", "icon": "factory"},
    {"symbol": "VCB.VN", "label": "Vietcombank", "icon": "landmark"},
    {"symbol": "TCB.VN", "label": "Techcombank", "icon": "banknote"},
    {"symbol": "MWG.VN", "label": "Thế Giới Di Động", "icon": "smartphone"},
    {"symbol": "VIC.VN", "label": "Vingroup", "icon": "building"},
    {"symbol": "VHM.VN", "label": "Vinhomes", "icon": "home"},
]


def _now_label() -> str:
    return datetime.now(LOCAL_TZ).strftime("%d/%m %H:%M")


def _fetch_index_history(symbol: str, *, days: int = 90) -> dict[str, Any] | None:
    """Pull daily OHLC for one index from VNDirect's dchart proxy."""

    now = int(time.time())
    url = "https://dchart-api.vndirect.com.vn/dchart/history"
    params = {
        "resolution": "D",
        "symbol": symbol,
        "from": str(now - days * 86400),
        "to": str(now),
    }
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return None

    if data.get("s") != "ok":
        return None

    times = data.get("t") or []
    closes = data.get("c") or []
    if not times or not closes:
        return None

    # Last two closes give us the daily change.
    last_close = float(closes[-1])
    prev_close = float(closes[-2]) if len(closes) >= 2 else last_close
    change = last_close - prev_close
    change_pct = (change / prev_close * 100) if prev_close else 0.0

    history = [{"ts": int(ts), "value": float(value)} for ts, value in zip(times, closes, strict=False)]

    return {
        "last_close": last_close,
        "prev_close": prev_close,
        "change": change,
        "change_percent": change_pct,
        "session_history": history,
    }


def fetch_stock_indices() -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for spec in INDICES:
        snapshot = _fetch_index_history(spec["symbol"])
        if snapshot is None:
            continue

        cards.append(
            {
                "key": f"stock_{spec['symbol'].lower()}",
                "label": spec["label"],
                "provider": "VNDirect",
                "symbol": spec["symbol"],
                "icon": spec["icon"],
                "price": snapshot["last_close"],
                "change": snapshot["change"],
                "change_percent": snapshot["change_percent"],
                "price_text": f"{snapshot['last_close']:,.2f}".replace(",", "."),
                "change_text": _format_change(snapshot["change"], snapshot["change_percent"]),
                "unit": "điểm",
                "updated_label": _now_label(),
                "source_url": f"https://vndirect.com.vn/portal/cong-cu/du-lieu-truc-tuyen.shtml#{spec['symbol']}",
                "session_history": snapshot["session_history"],
            }
        )

    # Fetch individual VN stocks via Yahoo Finance.
    for spec in VN_STOCKS:
        stock_data = _fetch_yahoo_stock(spec["symbol"])
        if stock_data is None:
            continue
        cards.append(
            {
                "key": f"stock_{spec['symbol'].replace('.', '_').lower()}",
                "label": spec["label"],
                "provider": "Yahoo",
                "symbol": spec["symbol"],
                "icon": spec["icon"],
                "price": stock_data["price"],
                "change": stock_data["change"],
                "change_percent": stock_data["change_percent"],
                "price_text": f"{stock_data['price']:,.0f}".replace(",", "."),
                "change_text": _format_change(stock_data["change"], stock_data["change_percent"]),
                "unit": "VND",
                "updated_label": _now_label(),
                "source_url": f"https://finance.yahoo.com/quote/{spec['symbol']}",
                "session_history": stock_data.get("history", []),
            }
        )
    return cards


def _fetch_yahoo_stock(symbol: str) -> dict[str, Any] | None:
    """Fetch a single stock price + 30-day history from Yahoo Finance."""

    from urllib.parse import quote

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}"
    try:
        response = requests.get(
            url,
            params={"range": "3mo", "interval": "1d", "includePrePost": "false"},
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return None

    result = data.get("chart", {}).get("result", [])
    if not result:
        return None
    meta = result[0].get("meta", {})
    price = meta.get("regularMarketPrice")
    prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")
    currency = meta.get("currency") or "USD"
    if price is None:
        return None
    change = (price - prev_close) if prev_close else 0
    change_pct = (change / prev_close * 100) if prev_close else 0

    # Extract daily close history for sparkline.
    timestamps = result[0].get("timestamp") or []
    quotes = (result[0].get("indicators", {}).get("quote") or [{}])[0]
    closes = quotes.get("close") or []
    history = []
    for ts, close in zip(timestamps, closes, strict=False):
        if close is not None:
            history.append({"ts": int(ts), "value": float(close)})

    return {
        "price": float(price),
        "change": float(change),
        "change_percent": float(change_pct),
        "currency": currency,
        "history": history,
    }


def _format_change(value: float, percent: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:,.2f} ({sign}{percent:.2f}%)".replace(",", ".")


def get_stocks_payload(*, force: bool = False) -> dict[str, Any]:
    cache_key = "stocks"
    if not force:
        cached = CACHE.get(cache_key)
        if cached:
            return cached

    cards = fetch_stock_indices()
    formatted: list[dict[str, Any]] = []
    for card in cards:
        record_price(card["key"], card.get("price"), label=card["label"])
        # Prefer the source with more distinct values for a meaningful chart.
        own = get_history(card["key"])
        session = card.get("session_history", [])
        own_unique = len({p["value"] for p in own}) if own else 0
        session_unique = len({p["value"] for p in session}) if session else 0
        history = session if session_unique > own_unique else own
        card_out = {**card, "history": history[-200:]}
        card_out.pop("session_history", None)
        formatted.append(card_out)

    payload = {
        "generated_at": datetime.now(LOCAL_TZ).isoformat(),
        "cards": formatted,
    }
    CACHE.set(cache_key, payload, config.PRICE_REFRESH_SECONDS)
    return payload
