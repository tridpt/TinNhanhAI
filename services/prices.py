from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import requests

import config

from .cache import TTLCache
from .vn_prices import get_vn_prices

UTC = UTC
LOCAL_TZ = timezone(timedelta(hours=7))
CACHE = TTLCache(namespace="prices")
USER_AGENT = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TinNhanhAI/1.0"}


def _fmt_dt(ts: int | None) -> str:
    if not ts:
        return ""
    return datetime.fromtimestamp(int(ts), tz=UTC).astimezone(LOCAL_TZ).strftime("%d/%m %H:%M")


def _fmt_value(value: float | None, precision: int = 2) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return f"{value:,.{precision}f}"


def _fmt_change(value: float | None, percent: float | None, precision: int = 2) -> str:
    if value is None:
        return ""
    sign = "+" if value >= 0 else ""
    pct = ""
    if percent is not None:
        pct = f" ({sign}{percent:.2f}%)"
    return f"{sign}{value:,.{precision}f}{pct}"


def _yahoo_chart(symbol: str) -> dict[str, Any]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}"
    response = requests.get(
        url,
        params={
            "range": "1d",
            "interval": "1d",
            "includePrePost": "false",
            "corsDomain": "finance.yahoo.com",
        },
        headers=USER_AGENT,
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    result = data["chart"]["result"][0]
    meta = result.get("meta", {})
    quote_data = (result.get("indicators", {}).get("quote") or [{}])[0]
    closes = [value for value in quote_data.get("close", []) if value is not None]
    price = meta.get("regularMarketPrice")
    if price is None and closes:
        price = closes[-1]
    previous_close = meta.get("chartPreviousClose") or meta.get("regularMarketPreviousClose")
    if previous_close is None and len(closes) >= 2:
        previous_close = closes[-2]
    change = None
    change_percent = None
    if price is not None and previous_close not in (None, 0):
        change = price - previous_close
        change_percent = (change / previous_close) * 100
    return {
        "symbol": symbol,
        "currency": meta.get("currency") or "USD",
        "price": float(price) if price is not None else None,
        "previous_close": float(previous_close) if previous_close is not None else None,
        "change": float(change) if change is not None else None,
        "change_percent": float(change_percent) if change_percent is not None else None,
        "updated_at": _fmt_dt(meta.get("regularMarketTime")),
        "market_state": meta.get("marketState") or "",
        "exchange_name": meta.get("exchangeName") or "",
    }


def get_prices_payload(*, force: bool = False) -> dict[str, Any]:
    cache_key = "prices"
    if not force:
        cached = CACHE.get(cache_key)
        if cached:
            return cached

    cards: list[dict[str, Any]] = []
    for spec in config.PRICE_SPECS:
        try:
            quote_data = _yahoo_chart(spec["symbol"])
            quote_data.update(
                {
                    "key": spec["key"],
                    "label": spec["label"],
                    "unit": spec["unit"],
                    "icon": spec["icon"],
                    "precision": spec["precision"],
                    "price_text": _fmt_value(quote_data["price"], spec["precision"]),
                    "change_text": _fmt_change(
                        quote_data["change"], quote_data["change_percent"], spec["precision"]
                    ),
                    "source_url": f"https://finance.yahoo.com/quote/{spec['symbol']}",
                }
            )
        except Exception as exc:
            quote_data = {
                "key": spec["key"],
                "label": spec["label"],
                "symbol": spec["symbol"],
                "unit": spec["unit"],
                "icon": spec["icon"],
                "precision": spec["precision"],
                "price": None,
                "price_text": "",
                "change": None,
                "change_percent": None,
                "change_text": "",
                "updated_at": "",
                "market_state": "",
                "exchange_name": "",
                "source_url": f"https://finance.yahoo.com/quote/{spec['symbol']}",
                "error": str(exc),
            }
        cards.append(quote_data)

    payload = {
        "generated_at": datetime.now(LOCAL_TZ).isoformat(),
        "cards": cards,
        "vn_cards": get_vn_prices(force=force).get("cards", []),
    }
    CACHE.set(cache_key, payload, config.PRICE_REFRESH_SECONDS)
    return payload

