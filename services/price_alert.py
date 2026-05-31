"""Background watcher that fires Telegram messages when a price threshold is hit.

Reuses the Telegram credentials from :mod:`services.telegram_alert`
(``TELEGRAM_BOT_TOKEN`` / ``TELEGRAM_CHAT_ID``). Runs in its own daemon thread
and polls live prices every ``PRICE_ALERT_POLL_SECONDS`` (default 300s).
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

from . import alerts as alert_store


def collect_current_prices() -> dict[str, dict[str, Any]]:
    """Gather the latest price for every alertable item, keyed by ``item_key``.

    Covers world commodities, VN gold/petrol, forex, crypto, and stocks.
    Each value is ``{"price": float, "label": str, "unit": str}``.
    """

    out: dict[str, dict[str, Any]] = {}

    def _add(card: dict[str, Any]) -> None:
        key = card.get("key")
        price = card.get("price")
        # VN cards use buy/sell instead of a single price.
        if price is None:
            price = card.get("sell") or card.get("buy")
        if key and price is not None:
            out[key] = {
                "price": float(price),
                "label": card.get("label", key),
                "unit": card.get("unit", ""),
            }

    try:
        from .prices import get_prices_payload

        prices = get_prices_payload()
        for card in prices.get("cards", []):
            _add(card)
        for card in prices.get("vn_cards", []):
            _add(card)
        for card in prices.get("forex_cards", []):
            _add(card)
    except Exception:
        pass

    try:
        from .crypto import get_crypto_payload

        for card in get_crypto_payload().get("cards", []):
            _add(card)
    except Exception:
        pass

    try:
        from .stocks import get_stocks_payload

        for card in get_stocks_payload().get("cards", []):
            _add(card)
    except Exception:
        pass

    return out


def _send_telegram(text: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not (token and chat_id):
        return False
    import requests

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
        r.raise_for_status()
        return True
    except Exception:
        return False


def scan_once(*, notify: bool = True) -> list[dict[str, Any]]:
    """Check all active alerts against live prices. Returns the ones triggered."""

    active = alert_store.list_alerts(active_only=True)
    if not active:
        return []

    prices = collect_current_prices()
    triggered: list[dict[str, Any]] = []

    for alert in active:
        info = prices.get(alert["item_key"])
        if not info:
            continue
        price = info["price"]
        if alert_store.is_crossed(alert["direction"], price, alert["threshold"]):
            alert_store.mark_triggered(alert["id"], price)
            payload = {**alert, "current_price": price, "label": alert["label"] or info["label"]}
            triggered.append(payload)
            if notify:
                arrow = "📈" if alert["direction"] == "above" else "📉"
                cond = "≥" if alert["direction"] == "above" else "≤"
                _send_telegram(
                    f"{arrow} <b>{payload['label']}</b>\n"
                    f"Giá hiện tại: <b>{price:,.2f}</b> {alert['unit']}\n"
                    f"Đã {cond} ngưỡng {alert['threshold']:,.2f}"
                )
    return triggered


def run_forever() -> None:
    interval = max(60, int(os.getenv("PRICE_ALERT_POLL_SECONDS", "300")))
    print(f"[price-alert] watcher started, interval={interval}s")
    while True:
        try:
            hits = scan_once()
            if hits:
                print(f"[price-alert] triggered {len(hits)} alert(s)")
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[price-alert] scan failed: {exc}")
        time.sleep(interval)


_started = False
_lock = threading.Lock()


def start_in_background() -> bool:
    """Spawn the watcher thread once if Telegram credentials are present."""

    global _started
    with _lock:
        if _started:
            return True
        if not (os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID")):
            return False
        thread = threading.Thread(target=run_forever, name="price-alert-watcher", daemon=True)
        thread.start()
        _started = True
        return True
