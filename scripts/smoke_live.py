#!/usr/bin/env python
"""Manual live smoke test — hits the *real* upstream sources.

Unlike the pytest suite (fully mocked, no network), this script deliberately
reaches out to VnExpress/RSS, Yahoo Finance, Binance, Vietcombank, Open-Meteo
and DuckDuckGo to confirm each source is still reachable and returning usable
data. Run it by hand whenever a feed looks stale or before a release.

    python scripts/smoke_live.py
    python scripts/smoke_live.py --json    # machine-readable summary

Exit code is 0 when every REQUIRED source is healthy, 1 otherwise. Sources
flagged optional (web search, weather) only downgrade to a warning so a flaky
third party doesn't fail the whole run.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Make ``services`` importable when run from anywhere.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _walk(obj):
    """Yield every dict nested anywhere inside ``obj``."""

    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _walk(value)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            yield from _walk(item)


def _count_prices(payload, keys=("price",)) -> int:
    """Count cards that carry a real numeric value under one of ``keys``.

    Sources name the number differently: world/crypto/stock cards use ``price``
    while Vietnamese gold and forex cards use ``buy``/``sell``. Restricting the
    keys per check keeps counts accurate (the world-prices payload also embeds
    VN cards, so counting every kind would overcount).
    """

    def _is_live(node) -> bool:
        return any(isinstance(node.get(key), (int, float)) and node.get(key) for key in keys)

    return sum(1 for node in _walk(payload) if _is_live(node))


def _count_articles(payload) -> int:
    """Count article-shaped dicts (have both a title and a url)."""

    return sum(1 for node in _walk(payload) if node.get("title") and node.get("url"))


# ── Individual checks ────────────────────────────────────────────────────────
# Each returns (healthy: bool, detail: str). Raising is caught by the runner.


def check_news():
    from services.news import get_topic_payload

    payload = get_topic_payload("all", force=True)
    n = _count_articles(payload)
    return n > 0, f"{n} bài từ RSS"


def check_world_prices():
    from services.prices import get_prices_payload

    payload = get_prices_payload(force=True)
    n = _count_prices(payload)
    return n > 0, f"{n} giá thế giới (Yahoo)"


def check_crypto():
    from services.crypto import get_crypto_payload

    payload = get_crypto_payload(force=True)
    n = _count_prices(payload)
    return n > 0, f"{n} coin (Binance)"


def check_stocks():
    from services.stocks import get_stocks_payload

    payload = get_stocks_payload(force=True)
    n = _count_prices(payload)
    return n > 0, f"{n} mã/chỉ số"


def check_vn_prices():
    from services.vn_prices import get_vn_prices

    payload = get_vn_prices(force=True)
    n = _count_prices(payload, keys=("buy", "sell"))
    return n > 0, f"{n} mục vàng/tỷ giá VN"


def check_weather():
    from services.weather import get_weather_payload

    payload = get_weather_payload(force=True)
    ok = isinstance(payload, dict) and bool(payload) and not payload.get("error")
    return ok, "ok" if ok else f"error: {payload.get('error') if isinstance(payload, dict) else 'no data'}"


def check_web_search():
    from services.search import search_general_web

    payload = search_general_web("thời tiết hà nội hôm nay")
    results = payload.get("results") if isinstance(payload, dict) else None
    n = len(results) if isinstance(results, list) else 0
    return n > 0, f"{n} kết quả (DuckDuckGo)"


# name, function, required?
CHECKS = [
    ("news", check_news, True),
    ("world_prices", check_world_prices, True),
    ("crypto", check_crypto, True),
    ("stocks", check_stocks, False),
    ("vn_prices", check_vn_prices, False),
    ("weather", check_weather, False),
    ("web_search", check_web_search, False),
]


def run() -> list[dict]:
    rows = []
    for name, fn, required in CHECKS:
        started = time.perf_counter()
        try:
            healthy, detail = fn()
            error = None
        except Exception as exc:  # network / parsing blew up entirely
            healthy, detail, error = False, "", f"{type(exc).__name__}: {exc}"
        elapsed = round(time.perf_counter() - started, 2)
        rows.append(
            {
                "source": name,
                "required": required,
                "healthy": healthy,
                "detail": detail,
                "error": error,
                "seconds": elapsed,
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = parser.parse_args()

    rows = run()

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print("=" * 60)
        print("TinNhanh AI — live source smoke test")
        print("=" * 60)
        for row in rows:
            if row["healthy"]:
                mark = "OK  "
            elif row["required"]:
                mark = "FAIL"
            else:
                mark = "WARN"
            tag = "" if row["required"] else " (optional)"
            info = row["detail"] or row["error"] or ""
            print(f"[{mark}] {row['source']:<13}{tag:<11} {info}  ({row['seconds']}s)")
        print("=" * 60)

    # Fail the run only when a *required* source is down.
    failed_required = [r for r in rows if r["required"] and not r["healthy"]]
    if failed_required:
        names = ", ".join(r["source"] for r in failed_required)
        print(f"\nREQUIRED sources down: {names}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
