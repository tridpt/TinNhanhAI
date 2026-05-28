"""Aggregate Vietnamese gold prices from multiple providers.

Each provider exposes a ``fetch_*`` function returning a list of normalized
price cards. Failures are swallowed so a flaky source never breaks the
dashboard. The top-level :func:`fetch_all_vn_gold` runs every provider
sequentially (network calls already cap at ~10s each) and merges results.

Price cards share the same shape as the international price cards in
``services/prices.py`` so the frontend can render them uniformly:

    {
        "key":   stable id used for history storage,
        "label": human-readable label,
        "provider":  short provider tag,
        "buy":   number (VND/lượng) or None,
        "sell":  number (VND/lượng) or None,
        "icon":  lucide icon name,
        "unit":  "VND/lượng",
        "source_url": web page,
        "updated_label": "DD/MM HH:MM",
    }
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

LOCAL_TZ = timezone(timedelta(hours=7))
TIMEOUT = 12

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "vi,en;q=0.8",
}


def _now_label() -> str:
    return datetime.now(LOCAL_TZ).strftime("%d/%m %H:%M")


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    cleaned = re.sub(r"[^\d.,-]", "", text)
    if not cleaned:
        return None
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif cleaned.count(".") > 1:
        cleaned = cleaned.replace(".", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


# Map each PNJ product code to (display label, lucide icon).
# Kept short so the dashboard does not flood with near-duplicate cards;
# users rarely care about the difference between PNJ-branded gold variants.
_PNJ_LABELS: dict[str, tuple[str, str]] = {
    "SJC":  ("Vàng SJC (PNJ)", "crown"),
    "N24K": ("Nhẫn Trơn PNJ 999.9", "circle-dot"),
    "PNJ":  ("Vàng PNJ Phượng Hoàng", "feather"),
    "24K":  ("Vàng nữ trang 24K (PNJ)", "gem"),
}

_SJC_TARGET_TYPES = ("Vàng SJC 1L, 10L, 1KG", "Vàng SJC 1L, 10L, 1 KG")


def fetch_pnj() -> list[dict[str, Any]]:
    url = "https://edge-api.pnj.io/ecom-frontend/v1/get-gold-price"
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return []

    cards: list[dict[str, Any]] = []
    for row in payload.get("data") or []:
        code = str(row.get("masp") or "").upper()
        if code not in _PNJ_LABELS:
            continue
        label, icon = _PNJ_LABELS[code]
        # PNJ values are in nghìn đồng per chỉ (1 lượng = 10 chỉ),
        # so multiply by 10_000 to normalize to VND/lượng.
        buy = _to_float(row.get("giamua"))
        sell = _to_float(row.get("giaban"))
        if buy is None and sell is None:
            continue
        cards.append(
            {
                "key": f"vn_gold_pnj_{code.lower()}",
                "label": label,
                "provider": "PNJ",
                "buy": buy * 10_000 if buy is not None else None,
                "sell": sell * 10_000 if sell is not None else None,
                "icon": icon,
                "unit": "VND/lượng",
                "source_url": "https://giavang.pnj.com.vn/",
                "updated_label": _now_label(),
            }
        )
    return cards


def fetch_sjc() -> list[dict[str, Any]]:
    url = "https://sjc.com.vn/GoldPrice/Services/PriceService.ashx"
    headers = {
        **HEADERS,
        "Origin": "https://sjc.com.vn",
        "Referer": "https://sjc.com.vn/giavang",
        "X-Requested-With": "XMLHttpRequest",
    }
    try:
        response = requests.post(
            url,
            data={"method": "GetSJCGoldPriceByDate", "toDate": ""},
            headers=headers,
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return []

    cards: list[dict[str, Any]] = []
    rows = payload.get("data") or []
    for row in rows:
        type_name = str(row.get("TypeName") or "")
        branch = str(row.get("BranchName") or "")
        if not any(target in type_name for target in _SJC_TARGET_TYPES):
            continue
        if "Hồ Chí Minh" not in branch and "HCM" not in branch:
            continue
        buy = _to_float(row.get("BuyValue") or row.get("Buy"))
        sell = _to_float(row.get("SellValue") or row.get("Sell"))
        if buy is None and sell is None:
            continue
        cards.append(
            {
                "key": "vn_gold_sjc_official",
                "label": "Vàng SJC (HCM)",
                "provider": "SJC",
                "buy": buy,
                "sell": sell,
                "icon": "crown",
                "unit": "VND/lượng",
                "source_url": "https://sjc.com.vn/giavang",
                "updated_label": _now_label(),
            }
        )
        break  # Only need the first matching SJC HCM row.
    return cards


# Keywords used to pick interesting BTMC products out of their large catalog.
_BTMC_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"VÀNG MIẾNG SJC", re.I), "Vàng SJC (BTMC)", "crown"),
    (re.compile(r"VÀNG MIẾNG VRTL", re.I), "Vàng VRTL (Bảo Tín Minh Châu)", "shield"),
    (re.compile(r"NHẪN TRÒN TRƠN", re.I), "Nhẫn Tròn Trơn BTMC", "circle-dot"),
    (re.compile(r"TRANG SỨC.*999\.9", re.I), "Trang sức vàng 999.9 (BTMC)", "gem"),
]


def fetch_btmc() -> list[dict[str, Any]]:
    """Pick a few representative products from the BTMC public price feed.

    BTMC returns ~70 products with row-indexed keys (``@n_1``, ``@pb_1`` etc).
    We flatten them into rows then match a small whitelist of patterns so the
    dashboard stays compact.
    """

    url = "http://api.btmc.vn/api/BTMCAPI/getpricebtmc?key=3kd8h1yec9jvf96vh9hd"
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return []

    raw_rows = ((payload.get("DataList") or {}).get("Data")) or []
    products: list[dict[str, Any]] = []
    for row in raw_rows:
        row_index = row.get("@row")
        if not row_index:
            continue
        name = row.get(f"@n_{row_index}") or ""
        buy = row.get(f"@pb_{row_index}") or ""
        sell = row.get(f"@ps_{row_index}") or ""
        products.append({"name": str(name), "buy": buy, "sell": sell})

    cards: list[dict[str, Any]] = []
    seen_labels: set[str] = set()
    for pattern, label, icon in _BTMC_PATTERNS:
        # Skip silver entries even if they happen to match (defensive).
        match = next(
            (
                p
                for p in products
                if pattern.search(p["name"])
                and "BẠC" not in p["name"].upper()
                and " AG " not in f" {p['name'].upper()} "
            ),
            None,
        )
        if not match or label in seen_labels:
            continue
        # BTMC values are đồng per chỉ; multiply by 10 for VND/lượng.
        buy = _to_float(match["buy"])
        sell = _to_float(match["sell"])
        if buy is None and sell is None:
            continue
        slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
        cards.append(
            {
                "key": f"vn_gold_btmc_{slug}",
                "label": label,
                "provider": "BTMC",
                "buy": buy * 10 if buy is not None else None,
                "sell": sell * 10 if sell is not None else None,
                "icon": icon,
                "unit": "VND/lượng",
                "source_url": "https://giavang.btmc.vn/",
                "updated_label": _now_label(),
            }
        )
        seen_labels.add(label)
    return cards


def fetch_all_vn_gold() -> list[dict[str, Any]]:
    """Run all providers and return a merged, deduped list of cards."""

    results: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for fetcher in (fetch_sjc, fetch_pnj, fetch_btmc):
        try:
            for card in fetcher():
                key = card.get("key")
                if not key or key in seen_keys:
                    continue
                seen_keys.add(key)
                results.append(card)
        except Exception:  # pragma: no cover - defensive
            continue
    return results
