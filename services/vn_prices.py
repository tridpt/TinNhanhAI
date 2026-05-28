"""Scrapers for Vietnam-specific market data.

Each fetcher is best-effort: if a source changes layout or is unreachable,
the function returns ``None`` rather than raising so the dashboard stays up.
All fetchers are wrapped behind :func:`get_vn_prices` which caches results
per :data:`config.PRICE_REFRESH_SECONDS`.

Notes on reliability:
- SJC (vàng SJC HCM): blocked by Cloudflare on plain HTTP. We attempt the
  JSON endpoint and HTML fallback but expect occasional ``None``.
- Petrolimex (giá xăng): the homepage popup renders prices via JS, so we
  scan static markup and gracefully return an empty list if nothing is found.
- Vietcombank (USD/VND): public JSON feed, very stable.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup

import config

from .cache import TTLCache

LOCAL_TZ = timezone(timedelta(hours=7))
CACHE = TTLCache(namespace="vn_prices")
USER_AGENT = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "vi,en;q=0.8",
}

REQUEST_TIMEOUT = 15


def _now_label() -> str:
    return datetime.now(LOCAL_TZ).strftime("%d/%m %H:%M")


def _parse_vn_number(text: str) -> float | None:
    if not text:
        return None
    cleaned = re.sub(r"[^\d.,-]", "", text)
    if not cleaned:
        return None
    has_comma = "," in cleaned
    if has_comma:
        # Vietnamese style: "1.234.567,89" -> "." is thousand sep, "," is decimal.
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif cleaned.count(".") == 1 and len(cleaned.split(".")[1]) <= 2:
        # US style: "26143.00" - keep "." as decimal point.
        pass
    else:
        # Multiple dots or trailing 3-digit group -> thousand separator.
        cleaned = cleaned.replace(".", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def fetch_sjc_gold() -> dict[str, Any] | None:
    """Pull SJC gold price.

    SJC's public site is behind Cloudflare's anti-bot challenge so a plain
    HTTP request often returns 403. We try the public JSON endpoint first,
    fall back to the HTML table, and finally give up gracefully.
    Set ``SJC_DISABLED=1`` in the environment to skip this fetch entirely.
    """

    if os.getenv("SJC_DISABLED", "").lower() in {"1", "true", "yes"}:
        return None

    url = "https://sjc.com.vn/GoldPrice/Services/PriceService.ashx"
    headers = {
        **USER_AGENT,
        "Origin": "https://sjc.com.vn",
        "Referer": "https://sjc.com.vn/giavang",
        "X-Requested-With": "XMLHttpRequest",
    }
    try:
        response = requests.post(
            url,
            data={"method": "GetSJCGoldPriceByDate", "toDate": ""},
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return _fetch_sjc_html_fallback()

    rows = data.get("data") or []
    sjc_row = next(
        (
            row
            for row in rows
            if "SJC" in str(row.get("TypeName", "")).upper()
            and "HỒ CHÍ MINH" in str(row.get("BranchName", "")).upper()
        ),
        rows[0] if rows else None,
    )
    if not sjc_row:
        return None

    buy = _parse_vn_number(str(sjc_row.get("Buy", "")))
    sell = _parse_vn_number(str(sjc_row.get("Sell", "")))
    if buy is None and sell is None:
        return None
    return {
        "key": "vn_gold_sjc",
        "label": "Vàng SJC (HCM)",
        "icon": "crown",
        "buy": buy,
        "sell": sell,
        "unit": "VND/lượng",
        "updated_label": _now_label(),
        "source_url": "https://sjc.com.vn/giavang",
    }


def _fetch_sjc_html_fallback() -> dict[str, Any] | None:
    try:
        response = requests.get(
            "https://sjc.com.vn/giavang",
            headers=USER_AGENT,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except Exception:
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.find("table")
    if not table:
        return None
    target_row = None
    for row in table.find_all("tr"):
        text = row.get_text(" ", strip=True).upper()
        if "SJC" in text and ("HCM" in text or "HỒ CHÍ MINH" in text):
            target_row = row
            break
    if target_row is None:
        return None
    cells = [cell.get_text(strip=True) for cell in target_row.find_all("td")]
    numbers = [value for value in (_parse_vn_number(cell) for cell in cells) if value]
    if len(numbers) < 2:
        return None
    return {
        "key": "vn_gold_sjc",
        "label": "Vàng SJC (HCM)",
        "icon": "crown",
        "buy": numbers[0] * 1000,
        "sell": numbers[1] * 1000,
        "unit": "VND/lượng",
        "updated_label": _now_label(),
        "source_url": "https://sjc.com.vn/giavang",
    }


def fetch_usd_vnd() -> dict[str, Any] | None:
    """Pull Vietcombank USD buy/sell rate from public exrate JSON feed."""

    today = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")
    url = (
        "https://www.vietcombank.com.vn/api/exchangerates"
        f"?date={today}"
    )
    try:
        response = requests.get(url, headers=USER_AGENT, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return _fetch_usd_open_er()

    rates = data.get("Data") or []
    usd_row = next(
        (row for row in rates if str(row.get("currencyCode", "")).upper() == "USD"),
        None,
    )
    if not usd_row:
        return _fetch_usd_open_er()

    buy_cash = _parse_vn_number(str(usd_row.get("cash", "")))
    buy_transfer = _parse_vn_number(str(usd_row.get("transfer", "")))
    sell = _parse_vn_number(str(usd_row.get("sell", "")))
    if not any((buy_cash, buy_transfer, sell)):
        return _fetch_usd_open_er()
    return {
        "key": "usd_vnd",
        "label": "USD/VND (Vietcombank)",
        "icon": "banknote",
        "buy": buy_transfer or buy_cash,
        "sell": sell,
        "unit": "VND/USD",
        "updated_label": _now_label(),
        "source_url": "https://www.vietcombank.com.vn/vi-VN/KHCN/Cong-cu-Tien-ich/Ty-gia",
    }


def _fetch_usd_open_er() -> dict[str, Any] | None:
    """Fallback to the free open.er-api.com feed (no auth required)."""

    try:
        response = requests.get(
            "https://open.er-api.com/v6/latest/USD",
            headers=USER_AGENT,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return None

    vnd_rate = (data.get("rates") or {}).get("VND")
    if vnd_rate is None:
        return None
    rate = float(vnd_rate)
    return {
        "key": "usd_vnd",
        "label": "USD/VND (open.er-api)",
        "icon": "banknote",
        "buy": rate,
        "sell": rate,
        "unit": "VND/USD",
        "updated_label": _now_label(),
        "source_url": "https://www.exchangerate-api.com/",
    }


_PETROL_LABELS = {
    "RON 95": "Xăng RON 95-III",
    "RON95": "Xăng RON 95-III",
    "E5 RON 92": "Xăng E5 RON 92-II",
    "E5 RON92": "Xăng E5 RON 92-II",
}


def fetch_petrolimex() -> list[dict[str, Any]]:
    """Scrape current retail fuel prices from Petrolimex homepage table."""

    url = "https://www.petrolimex.com.vn/"
    try:
        response = requests.get(url, headers=USER_AGENT, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    rows = soup.select(".prices-area table tr")
    if not rows:
        rows = soup.select("table tr")

    extracted: dict[str, float] = {}
    for row in rows:
        cells = [cell.get_text(strip=True) for cell in row.find_all(["td", "th"])]
        if len(cells) < 2:
            continue
        product_name = cells[0].upper()
        for token, label in _PETROL_LABELS.items():
            if token in product_name and label not in extracted:
                price_value = _parse_vn_number(cells[1])
                if price_value:
                    extracted[label] = price_value
                break

    cards: list[dict[str, Any]] = []
    for label, price in extracted.items():
        key = "petrol_" + re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
        cards.append(
            {
                "key": key,
                "label": label,
                "icon": "fuel",
                "buy": None,
                "sell": price,
                "unit": "VND/lít",
                "updated_label": _now_label(),
                "source_url": "https://www.petrolimex.com.vn/",
            }
        )
    return cards


def get_vn_prices(*, force: bool = False) -> dict[str, Any]:
    cache_key = "vn_prices"
    if not force:
        cached = CACHE.get(cache_key)
        if cached:
            return cached

    cards: list[dict[str, Any]] = []
    gold = fetch_sjc_gold()
    if gold:
        cards.append(gold)
    fx = fetch_usd_vnd()
    if fx:
        cards.append(fx)
    cards.extend(fetch_petrolimex())

    payload = {
        "generated_at": datetime.now(LOCAL_TZ).isoformat(),
        "cards": [_format_card(card) for card in cards],
    }
    CACHE.set(cache_key, payload, config.PRICE_REFRESH_SECONDS)
    return payload


def _format_card(card: dict[str, Any]) -> dict[str, Any]:
    """Add display-ready strings while keeping raw numbers for AI prompts."""

    buy = card.get("buy")
    sell = card.get("sell")
    formatted = dict(card)
    formatted["buy_text"] = _format_vnd(buy) if buy is not None else ""
    formatted["sell_text"] = _format_vnd(sell) if sell is not None else ""
    if buy is not None and sell is not None and buy != sell:
        formatted["price_text"] = f"Mua {formatted['buy_text']} / Bán {formatted['sell_text']}"
    elif sell is not None:
        formatted["price_text"] = formatted["sell_text"]
    elif buy is not None:
        formatted["price_text"] = formatted["buy_text"]
    else:
        formatted["price_text"] = ""
    return formatted


def _format_vnd(value: float) -> str:
    return f"{value:,.0f}".replace(",", ".")
